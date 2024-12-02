import os
import json
import shutil
import subprocess
from enum import Enum

import rich
import typer
from InquirerPy import inquirer
from typing_extensions import Annotated

from ..heirloom import Heirloom, Console
from ..password_functions import *
from ..path_functions import *
from ..database_functions import *
from ..config import *


class InstallationMethod(str, Enum):
    wine = 'wine'
    sevenzip = '7zip'


class HeirloomManager:
    def __init__(self, config: dict, config_dir: str):
        self.app = typer.Typer()
        self.app.command(name="login")(self.login)
        self.app.command(name="refresh")(self.refresh)
        self.app.command(name="list")(self.list_games)
        self.app.command(name="download")(self.download_game)
        self.app.command(name="install")(self.install_game)
        self.app.command(name="info")(self.info)
        self.app.command(name="uninstall")(self.uninstall)
        self.app.command(name="launch")(self.launch)
        self._init_encryption()
        self._init_console()
        self.config_dir = config_dir
        self.config = config
        self.heirloom = Heirloom(**self.config)


    def __del__(self):
        if os.path.isdir(self.heirloom._tmp_dir):
            shutil.rmtree(self.heirloom._tmp_dir)


    def _init_encryption(self):
        encryption_key = get_encryption_key()
        if not encryption_key:
            set_encryption_key()
            encryption_key = get_encryption_key()


    def _init_console(self, quiet=False):
        self.console = Console(quiet=quiet)


    def merge_game_data_with_db(self):
        games = self.heirloom.games
        for each_game in games:
            record = read_game_record(self.config['db'], uuid=each_game['installer_uuid'])
            if not record:
                self.console.print(f':exclamation: Unable to read game record for UUID [green]{each_game["installer_uuid"]}[/green]!')
                record = read_game_record(self.config['db'], name=each_game['game_name'])
                if not record:
                    self.console.print(f':warning: Unable to read game record for game name [blue]{each_game["game_name"]}[/blue]!')
            if record:
                each_game['install_dir'] = record.get('install_dir', 'Not Installed')
                each_game['executable'] = record.get('executable', 'Not Installed')
        self.heirloom.games = games


    def select_from_games_list(self, installed_only=False):
        self.heirloom.refresh_games_list()
        games = self.heirloom.games
        if not installed_only:
            game = inquirer.select(message='Select a game: ', choices=[g['game_name'] for g in games]).execute()
        else:
            game = inquirer.select(message='Select a game: ', choices=[g['game_name'] for g in games if g['install_dir'] != 'Not Installed']).execute()
        return game


    def login(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False):
        """
        Log into your Legacy Games account.
        """
        self._init_console(quiet)
        try:
            with self.console.status('Logging in to Legacy Games...'):
                self.user_id = self.heirloom.login()
        except Exception as e:
            self.console.print(f':exclamation: Unable to log in to Legacy Games!')
            self.console.print(e)
            raise e


    def refresh(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False):
        """
        Refresh games in your Legacy Games library.
        """
        self.login(quiet)
        try:
            with self.console.status('Refreshing games list...'):
                self.heirloom.refresh_games_list()
            with self.console.status('Initializing database...'):
                self.config['db'] = init_games_db(self.config_dir, self.heirloom.games)
            with self.console.status('Merging database into game data...'):
                self.merge_game_data_with_db()
            refresh_game_installation_status(self.config['db'])
        except Exception as e:
            self.console.print(f':exclamation: Unable to refresh games list!')
            self.console.print(e)
            raise e


    def list_games(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False,
        installed: Annotated[bool, typer.Option('--installed', help='Only list installed games')] = False,
        not_installed: Annotated[bool, typer.Option('--not-installed', help='Only list games that are NOT installed')] = False,
        json_output: Annotated[bool, typer.Option('--json', help='Output the data in JSON format')] = False):
        """
        Lists games in your Legacy Games library.
        """
        self.refresh(quiet)
        if installed and not_installed:  # Two negatives makes a positive!
            installed = False
            not_installed = False
        refresh_game_installation_status(self.config['db'])
        games_list = []
        for g in self.heirloom.games:
            record = read_game_record(self.config['db'], name=g['game_name'])
            if record and record['install_dir'] != 'Not Installed':
                if not_installed:
                    continue
            elif record and record['install_dir'] == 'Not Installed':
                if installed:
                    continue
            game_data = {
                "game_name": g['game_name'],
                "uuid": g['installer_uuid'],
                "description": g['game_description']
            }
            games_list.append(g)
        if json_output:
            print(json.dumps(games_list, indent=4))
        else:
            table = rich.table.Table(title='Legacy Games', box=rich.box.ROUNDED, show_lines=True)
            table.add_column("Game Name", justify="left", style="yellow")
            table.add_column("UUID", justify="center", style="green")
            table.add_column('Description', justify="left", style="white bold")
            for game in games_list:
                table.add_row(game['game_name'], game['installer_uuid'], game['game_description'])
            self.console.print(table)


    def download_game(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False,
        game: Annotated[str, typer.Option(help='Game name to download, will be prompted if not provided')] = None,
        uuid: Annotated[str, typer.Option(help='UUID of game to download, will be prompted for game name if not provided')] = None):
        """
        Downloads a game from the Legacy Games library and saves the installation file to the current folder.
        """
        self.refresh(quiet)
        if uuid:
            game = self.heirloom.get_game_from_uuid(uuid)
        if not game:
            game = self.select_from_games_list()
        fn = self.heirloom.download_game(game, output_dir='./')
        self.console.print(f'Successfully downloaded [bold blue]{game}[/bold blue] setup executable as [green]{fn}[/green]')


    def install_game(
        self,
        game: Annotated[str, typer.Option(help='Game name to install, will be prompted if not provided')] = None,
        uuid: Annotated[str, typer.Option(help='UUID of game to install, will be prompted for game name if not provided')] = None,
        install_method: Annotated[InstallationMethod, typer.Option(case_sensitive=False)] = None):
        """
        Installs a game from the Legacy Games library.
        """
        self.refresh(quiet)
        refresh_game_installation_status(self.config['db'])
        self.merge_game_data_with_db()
        while not self.config.get('base_install_dir'):
            self.config['base_install_dir'] = input('Enter base installation folder: ')
        if not os.path.isdir(os.path.expanduser(self.config['base_install_dir'])):
            os.makedirs(os.path.expanduser(self.config['base_install_dir']))
        if not game and not uuid:
            game = self.select_from_games_list()
            uuid = self.heirloom.get_uuid_from_name(game)
        if uuid and not game:
            game = self.heirloom.get_game_from_uuid(uuid)
        if game and not uuid:
            uuid = self.heirloom.get_uuid_from_name(game)
        if install_method:
            result = self.heirloom.install_game(game, installation_method=install_method.value)
        else:
            result = self.heirloom.install_game(game)
        if result.get('status') == 'success':
            self.console.print(f'Installation to [green]{result["install_path"]}[/green] successful! :grin:')
            if result.get('executable_files') and len(result.get('executable_files')) == 1:
                executable_file = result.get('executable_files')[0].split('/')[-1]
                self.console.print(f'To start game, run: [yellow]{self.config["wine_path"]} \'{result.get("install_path")}\\{executable_file}\'')
                answer = f'{result.get("install_path")}\\{executable_file}'
            elif result.get('executable_files') and len(result.get('executable_files')) > 1:
                self.console.print(f':exclamation: Ambiguous executable detected!')
                answer = inquirer.select('Select the executable used to launch the game: ', choices=result.get('executable_files')).execute()
                executable_file = answer.split('/')[-1]
                self.console.print(f'To start game, run: [yellow]{self.config["wine_path"]} \'{result.get("install_path")}\\{executable_file}\'')
                answer = f'{result.get("install_path")}\\{executable_file}'
            write_game_record(self.config['db'], name=game, uuid=uuid, install_dir=result['install_path'], executable=answer)
        else:
            self.console.print(result)
            self.console.print(f'[bold]Installation was [red italic]unsuccessful[/red italic]! :frowning:')


    def info(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False,
        game: Annotated[str, typer.Option(help='Game name to download, will be prompted if not provided')] = None,
        uuid: Annotated[str, typer.Option(help='UUID of game to download, will be prompted for game name if not provided')] = None):
        """
        Prints a JSON blob representing a game from the Legacy Games API.
        """
        self.refresh(quiet)
        self.merge_game_data_with_db()
        if uuid:
            game = self.heirloom.get_game_from_uuid(uuid)
        if not game:
            game = self.select_from_games_list()
        print(json.dumps(self.heirloom.dump_game_data(game), indent=4))


    def uninstall(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False,
        game: Annotated[str, typer.Option(help='Game name to uninstall, will be prompted if not provided')] = None,
        uuid: Annotated[str, typer.Option(help='UUID of game to uninstall, will be prompted for game name if not provided')] = None):
        """
        Uninstalls a game from the Legacy Games library.
        """
        self.refresh(quiet)
        refresh_game_installation_status(self.config['db'])
        if uuid:
            game = self.heirloom.get_game_from_uuid(uuid)
        if not game:
            game = self.select_from_games_list(installed_only=True)
        result = self.heirloom.uninstall_game(game)
        if result.get('status') == 'success':
            self.console.print(f'Uninstallation of {game} successful! :grin:')
            delete_game_record(self.config['db'], uuid=uuid)
        else:
            self.console.print(result)
            self.console.print(f'[bold]Uninstallation was [red italic]unsuccessful[/red italic]! :frowning:')


    def launch(
        self,
        quiet: Annotated[bool, typer.Option('--quiet', help="Run without extra output")] = False,
        game: Annotated[str, typer.Option(help='Game name to uninstall, will be prompted if not provided')] = None,
        uuid: Annotated[str, typer.Option(help='UUID of game to uninstall, will be prompted for game name if not provided')] = None):
        """
        Launches an installed game.
        """
        self.refresh(quiet)
        if not game:
            game = self.select_from_games_list(installed_only=True)
        if uuid:
            game = self.heirloom.get_game_from_uuid(uuid)
        else:
            uuid = self.heirloom.get_uuid_from_name(game)
        record = read_game_record(self.config['db'], uuid=uuid)
        cmd = [self.config['wine_path'], f"'{record['executable']}'"]
        with self.console.status(f"Running: [yellow]{' '.join(cmd)}[/yellow]"):
            result = subprocess.run(cmd, capture_output=True)
            self.console.print(result.stdout.decode('utf-8'))

def main():
    """
    Initializes the HeirloomManager with the passed parameters.
    """
    config_dir = os.path.expanduser('~/.config/heirloom/')
    configparser = get_config(config_dir)
    config = dict(configparser['HeirloomGM'])
    manager = HeirloomManager(config, config_dir)
    manager.app()
