import asyncio
import sys
from pathlib import Path

import aiofiles
import click
from click_default_group import DefaultGroup
from loguru import logger

from wizwalker import Wad, WizWalker, utils
from wizwalker.cli import start_console


logger.enable("wizwalker")
logger.remove(0)

logfile = utils.get_logs_folder() / "debug.log"
logger.add(logfile, level="DEBUG", rotation="1 week", enqueue=True)


@click.group(cls=DefaultGroup, default="cli", default_if_no_args=True)
def main():
    """
    Wizwalker cli
    """
    pass
    # app = WizWalker()
    #
    # # close WizWalker when app is closed
    # atexit.register(app.close)
    #
    # app.run()


@main.command()
def cli():
    """
    Start a cli instance
    """
    if sys.platform != "win32":
        raise RuntimeError(f"This program is windows only, not {sys.platform}")

    walker = WizWalker()
    start_console(locals={"walker": walker})


# TODO: 2.0: remove --nowait, make start_instances_with_login not wait if there are no logins
@main.command()
@click.option(
    "--instances", default=1, show_default=True, help="Number of instances to start"
)
@click.argument("logins", nargs=-1)
@click.option(
    "--nowait", is_flag=True, default=False, help="Don't wait for completion of startup process",
)
def start_wiz(instances, logins, nowait):
    """
    Start multiple wizard101 instances and optionally login to them
    """
    num_logins = len(logins)
    if instances != num_logins and instances != 1:
        click.echo("Not enough or too many logins for the number of instances")
        exit(1)

    if num_logins > instances:
        instances = num_logins

    asyncio.run(utils.start_instances_with_login(instances, logins, wait_for_ready=not nowait))


@main.group()
def wad():
    """
    Wad manipulation commands
    """
    pass


# # TODO: finish
# @wad.command()
# def archive():
#     """
#     Create a wad from a directory
#     """
#     click.echo("Not implimented")


@wad.command(short_help="Unarchive a wad into a directory")
@click.argument("input_wad", type=str)
@click.argument("output_dir", type=click.Path(file_okay=False), default=".")
def unarchive(input_wad, output_dir):
    """
    Unarchive a wad into a directory

    input_wad automatically fills in the rest of the path so you only need the name; i.e "root"
    output_dir defaults to the current directory
    """
    wad_file = Wad.from_game_data(input_wad)
    path = Path(output_dir)

    if not path.exists():
        if click.confirm(f"{path} does not exsist; create it?", default=True):
            path.mkdir(exist_ok=True)
        else:
            exit(0)

    async def _unarchive_wad():
        # we don't use wad_file.unarchive so we can have this nice progress bar
        with click.progressbar(
            await wad_file.names(),
            show_pos=True,
            item_show_func=lambda i: i.split("/")[-1] if i else i,
            show_eta=False,
        ) as names:
            for file_name in names:
                dirs = file_name.split("/")
                # not a base level file
                if len(dirs) != 1:
                    current = path
                    for next_dir in dirs[:-1]:
                        current = current / next_dir
                        current.mkdir(exist_ok=True)

                file_path = path / file_name
                file_data = await wad_file.get_file(file_name)

                async with aiofiles.open(file_path, "wb") as fp:
                    await fp.write(file_data)

    asyncio.run(_unarchive_wad())


@wad.command(short_help="Extract a single file from a wad")
@click.argument("input_wad", type=str)
@click.argument("file_name")
def extract(input_wad, file_name):
    """
    Extract a single file from a wad

    input_wad automatically fills in the rest of the path so you only need the name; i.e "root"
    """
    wad_file = Wad.from_game_data(input_wad)

    async def _extract_file():
        try:
            file_data = await wad_file.get_file(file_name)
        except ValueError:
            click.echo(f"No file named {file_name} found.")
        else:
            relitive_file_name = file_name.split("/")[-1]

            async with aiofiles.open(relitive_file_name, "wb+") as fp:
                click.echo("Writing...")
                await fp.write(file_data)

    asyncio.run(_extract_file())


# # TODO: finish
# @wad.command()
# def insert():
#     """
#     Insert a single file into a wad
#     """
#     click.echo("Not implimented")


if __name__ == "__main__":
    main()
