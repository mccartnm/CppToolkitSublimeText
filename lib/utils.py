

import re
import os
import json

from .tokenize import CppTokenizer
from .details import CppRefactorDetails
from .meta import _BaseCppRefactorMeta
from .state import FunctionState

def _cache_path():
    import sublime
    return os.path.join(sublime.cache_path(), "CppRefactor")


def _write_menu(menu):
    import sublime
    menu_path = os.path.join(_cache_path(), "Context.sublime-menu")
    with open(menu_path, "w+") as cache:
        cache.write(json.dumps(menu, cache))

