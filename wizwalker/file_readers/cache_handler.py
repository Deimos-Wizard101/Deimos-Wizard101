import json
from collections import defaultdict
from functools import cached_property
from pathlib import Path
from typing import List, Optional, Union

import aiofiles
from loguru import logger

from wizwalker import utils
from .wad import Wad


class CacheHandler:
    def __init__(self):
        self._wad_cache = None
        self._template_ids = None
        self._node_cache = None

        self._root_wad = Wad.from_game_data("root")

    @cached_property
    def install_location(self) -> Path:
        """
        Wizard101 install location
        """
        return utils.get_wiz_install()

    @cached_property
    def cache_dir(self):
        """
        The dir parsed data is stored in
        """
        return utils.get_cache_folder()

    async def _check_updated(
        self, wad_file: Wad, files: Union[List[str], str]
    ) -> List[str]:
        if isinstance(files, str):
            files = [files]

        if not self._wad_cache:
            self._wad_cache = await self.get_wad_cache()

        res = []

        for file_name in files:
            file_info = await wad_file.get_file_info(file_name)

            if self._wad_cache[wad_file.name][file_name] != file_info.size:
                logger.info(
                    f"{file_name} has updated. old: {self._wad_cache[wad_file.name][file_name]} new: {file_info.size}"
                )
                res.append(file_name)
                self._wad_cache[wad_file.name][file_name] = file_info.size

            else:
                logger.info(f"{file_name} has not updated from {file_info.size}")

        return res

    async def check_updated(
        self, wad_file: Wad, files: Union[List[str], str]
    ) -> List[str]:
        """
        Checks if some wad files have changed since we last accessed them

        Returns:
            List of the file names that have updated
        """
        res = await self._check_updated(wad_file, files)

        if res:
            await self.write_wad_cache()

        return res

    # TODO: rename in 2.0 to _cache
    async def cache(self):
        """
        Caches various file data
        """
        root_wad = Wad.from_game_data("Root")

        logger.info("Caching template if needed")
        await self._cache_template(root_wad)

    async def _cache_template(self, root_wad):
        template_file = await self.check_updated(root_wad, "TemplateManifest.xml")

        if template_file:
            file_data = await root_wad.get_file("TemplateManifest.xml")
            pharsed_template_ids = utils.pharse_template_id_file(file_data)
            del file_data

            async with aiofiles.open(self.cache_dir / "template_ids.json", "w+") as fp:
                json_data = json.dumps(pharsed_template_ids)
                await fp.write(json_data)

    async def get_template_ids(self) -> dict:
        """
        Loads template ids from cache

        Returns:
            the loaded template ids
        """
        if self._template_ids is None:
            await self.cache()
            async with aiofiles.open(self.cache_dir / "template_ids.json") as fp:
                message_data = await fp.read()
            self._template_ids = json.loads(message_data)
        return self._template_ids

    @staticmethod
    def _parse_lang_file(file_data):
        try:
            decoded = file_data.decode("utf-16")

        # empty file
        except UnicodeDecodeError:
            return

        # splitlines splits whitespace that lang files should not recognize as a newline
        file_lines = decoded.split("\r\n")

        header, *lines = file_lines
        _, lang_name = header.split(":")

        lang_mapping = dict(zip(lines[::3], lines[2::3]))

        return {lang_name: lang_mapping}

    async def _get_all_lang_file_names(self, root_wad: Wad) -> List[str]:
        lang_file_names = []

        for file_name in await root_wad.names():
            if file_name.startswith("Locale/en-US/"):
                lang_file_names.append(file_name)

        return lang_file_names

    async def _read_lang_file(self, root_wad: Wad, lang_file: str):
        file_data = await root_wad.get_file(lang_file)
        parsed_lang = self._parse_lang_file(file_data)

        return parsed_lang

    async def _cache_lang_file(self, root_wad: Wad, lang_file: str):
        if not await self.check_updated(root_wad, lang_file):
            return
        parsed_lang = await self._read_lang_file(root_wad, lang_file)
        if parsed_lang is None:
            return

        lang_map = await self._get_langcode_map()
        lang_map.update(parsed_lang)
        async with aiofiles.open(self.cache_dir / "langmap.json", "w+") as fp:
            json_data = json.dumps(lang_map)
            await fp.write(json_data)

    async def _cache_lang_files(self, root_wad: Wad):
        lang_file_names = await self._get_all_lang_file_names(root_wad)

        parsed_lang_map = {}
        for file_name in lang_file_names:
            if not await self._check_updated(root_wad, file_name):
                continue
            parsed_lang = await self._read_lang_file(root_wad, file_name)
            if parsed_lang is not None:
                parsed_lang_map.update(parsed_lang)

        await self.write_wad_cache()
        lang_map = await self._get_langcode_map()
        lang_map.update(parsed_lang_map)
        async with aiofiles.open(self.cache_dir / "langmap.json", "w+") as fp:
            json_data = json.dumps(lang_map)
            await fp.write(json_data)

    async def _get_langcode_map(self) -> dict:
        try:
            async with aiofiles.open(self.cache_dir / "langmap.json") as fp:
                data = await fp.read()
                return json.loads(data)

        # file not found
        except OSError:
            return {}

    async def cache_all_langcode_maps(self):
        await self._cache_lang_files(self._root_wad)

    async def get_langcode_map(self) -> dict:
        """
        Gets the langcode map

        {lang_file_name: {code: value}}
        """
        return await self._get_langcode_map()

    async def get_wad_cache(self) -> dict:
        """
        Gets the wad cache data

        Returns:
            a dict with the current cache data
        """
        try:
            async with aiofiles.open(self.cache_dir / "wad_cache.data") as fp:
                data = await fp.read()

        # file not found
        except OSError:
            data = None

        wad_cache = defaultdict(lambda: defaultdict(lambda: -1))

        if data:
            wad_cache_data = json.loads(data)

            # this is so the default dict inside the default dict isn't replaced
            # by .update
            for k, v in wad_cache_data.items():
                for k1, v1 in v.items():
                    wad_cache[k][k1] = v1

        return wad_cache

    async def write_wad_cache(self):
        """
        Writes wad cache to disk
        """
        async with aiofiles.open(self.cache_dir / "wad_cache.data", "w+") as fp:
            json_data = json.dumps(self._wad_cache)
            await fp.write(json_data)

    async def get_template_name(self, template_id: int) -> Optional[str]:
        """
        Get the template name of something by id

        Args:
            template_id: The template id of the item

        Returns:
            str of the template name or None if there is no item with that id
        """
        template_ids = await self.get_template_ids()

        return template_ids.get(str(template_id))

    async def get_langcode_name(self, langcode: str):
        """
        Get the langcode name from the langcode i.e Spells_00001

        Args:
            langcode: Langcode in the format filename_code

        Raises:
            ValueError: If the langcode does not have a match

        """
        split_point = langcode.find("_")
        lang_filename = langcode[:split_point]
        code = langcode[split_point + 1 :]

        lang_files = await self._get_all_lang_file_names(self._root_wad)

        cached = False
        for filename in lang_files:
            if filename == f"Locale/en-US/{lang_filename}.lang":
                await self._cache_lang_file(self._root_wad, filename)
                cached = True
                break

        if not cached:
            raise ValueError(f"No lang file named {lang_filename}")

        langcode_map = await self.get_langcode_map()
        lang_file = langcode_map.get(lang_filename)

        if lang_file is None:
            raise ValueError(f"No lang file named {lang_filename}")

        lang_name = lang_file.get(code)

        if lang_name is None:
            raise ValueError(f"No lang name with code {code}")

        return lang_name

    # async def get_nav_data(self, zone_name: str):
    #     """
    #
    #     Args:
    #         zone_name:
    #
    #     Returns:
    #
    #     """
    #     pass
    #
    # async def write_nav_data(self):
    #     pass
