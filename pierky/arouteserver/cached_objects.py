# Copyright (C) 2017 Pier Carlo Chiodi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import time

from config.program import program_config
from .errors import CachedObjectsError


class CachedObject(object):

    def __init__(self, **kwargs):
        self.cache_dir = kwargs.get("cache_dir",
                                    program_config.get_cfg_file_path("cache_dir"))
        self.cache_expiry_time = program_config.cfg["cache_expiry_time"]
        self.raw_data = None

    def _get_object_filename(self):
        raise NotImplementedError()

    def _get_object_filepath(self):
        return os.path.join(self.cache_dir, self._get_object_filename())

    def load_data_from_cache(self):
        file_path = self._get_object_filepath()

        if not os.path.isfile(file_path):
            return False

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except:
            return False

        if not "ts" in data:
            return False
        if not "data" in data:
            return False

        epoch_time = int(time.time())

        if data["ts"] <= epoch_time - self.cache_expiry_time:
            return False

        self.raw_data = data["data"]
        return True

    def _get_data(self):
        raise NotImplementedError()

    def load_data(self):
        if self.load_data_from_cache():
            return

        self.raw_data = self._get_data()

        self.save_data_to_cache()

    def save_data_to_cache(self):
        file_path = self._get_object_filepath()

        epoch_time = int(time.time())

        cache_data = {
            "ts": epoch_time,
            "data": self.raw_data
        }

        if self.raw_data:
            try:
                with open(file_path, "w") as f:
                    json.dump(cache_data, f)
            except Exception as e:
                raise CachedObjectsError(
                    "Error while saving data to the cache: {}".format(str(e))
                )
