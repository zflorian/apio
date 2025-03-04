# -*- coding: utf-8 -*-
# -- This file is part of the Apio project
# -- (C) 2016-2019 FPGAwars
# -- Author Jesús Arroyo
# -- Licence GPLv2
# -- Derived from:
# ---- Platformio project
# ---- (C) 2014-2016 Ivan Kravets <me@ikravets.com>
# ---- Licence Apache v2
"""TODO"""


from email.utils import parsedate_tz
from math import ceil
from time import mktime
from pathlib import Path

import requests
import click


from apio import util

# pylint: disable=E1101
requests.packages.urllib3.disable_warnings()


class FDUnrecognizedStatusCode(util.ApioException):
    """TODO"""

    MESSAGE = "Got an unrecognized status code '{0}' when downloaded {1}"


class FileDownloader:
    """TODO"""

    CHUNK_SIZE = 1024

    def __init__(self, url, dest_dir=None):
        self._url = url
        self._fname = url.split("/")[-1]

        self._destination = self._fname
        if dest_dir:
            self.set_destination(str(Path(dest_dir) / self._fname))

        self._progressbar = None
        self._request = None

        # make connection
        self._request = requests.get(url, stream=True, timeout=5)
        if self._request.status_code != 200:
            raise FDUnrecognizedStatusCode(self._request.status_code, url)

    def set_destination(self, destination):
        """TODO"""

        self._destination = destination

    def get_filepath(self):
        """TODO"""
        return self._destination

    def get_lmtime(self):
        """TODO"""

        if "last-modified" in self._request.headers:
            return self._request.headers.get("last-modified")
        return None

    def get_size(self):
        """TODO"""

        return int(self._request.headers.get("content-length"))

    def start(self):
        """TODO"""

        itercontent = self._request.iter_content(chunk_size=self.CHUNK_SIZE)
        with open(self._destination, "wb") as file:
            chunks = int(ceil(self.get_size() / float(self.CHUNK_SIZE)))

            with click.progressbar(length=chunks, label="Downloading") as pbar:
                for _ in pbar:
                    file.write(next(itercontent))
        self._request.close()

        self._preserve_filemtime(self.get_lmtime())

    def _preserve_filemtime(self, lmdate):
        if lmdate is not None:
            timedata = parsedate_tz(lmdate)
            lmtime = mktime(timedata[:9])
            util.change_filemtime(self._destination, lmtime)

    def __del__(self):
        if self._request:
            self._request.close()
