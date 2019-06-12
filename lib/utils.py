

import os
import json
import sublime

def _cache_path():
    return os.path.join(sublime.cache_path(), "CppRefactor")


def _write_menu(menu):
    menu_path = os.path.join(_cache_path(), "Context.sublime-menu")
    with open(menu_path, "w+") as cache:
        cache.write(json.dumps(menu, cache))
