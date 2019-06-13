"""
Tools for auto declaring methods and classes from C++ headers
into the respective source and, eventually vis-versa
"""
import re
import os
import json
import sublime
import sublime_plugin

from .lib import utils
from .cpp_refactor_commands import _BaseCppCommand, CppRefactorDetails

__author__ = 'Michael McCartney'
__version__ = '0.0.2'


def plugin_loaded():
    os.makedirs(utils._cache_path(), exist_ok=True)
    utils._write_menu([])


def plugin_unloaded():
    try:
        os.remove(os.path.join(utils._cache_path(), "Context.sublime-menu"))
    except:
        pass

class CppRefactorListener(sublime_plugin.EventListener):
    """
    Event listener for handling context-aware menu creation depending
    on the selection and the lines of code present

    This is built to be modular and scale better than just be a one-trick pony
    """

    def _args_to_vec(self, args):
        return (args['event']['x'], args['event']['y'])


    def _context_line(self, view, pos):
        return view.substr(view.line(view.layout_to_text(pos)))

    def _previous_line(self, view, pos):
        return (pos[0], pos[1] - view.line_height())

    def _next_line(self, view, pos):
        return (pos[0], pos[1] + view.line_height())


    def _build_header_menu(self, view, command, args, pos, header, source):
        """
        Using the _BaseCppCommand registry of header-capable commands, we build a dynamic
        context menu that can act on the text we're setting out on.
        :return: list
        """
        original_position = pos[:]

        output = []

        current_word = view.substr(view.word(view.layout_to_text(pos)))
        current_line = self._context_line(view, pos)
        while not current_line.endswith(';'):
            pos = (pos[0], pos[1] + view.line_height())
            if pos[1] > view.layout_extent()[1]:
                break

            current_line += self._context_line(view, pos)

        after_one = False

        detail = CppRefactorDetails(
            view=view,
            command=command,
            args=args,
            pos=pos,
            current_file_type='header',
            current_word=current_word,
            current_line=current_line,
            header=header,
            source=source
        )

        for possible_command in _BaseCppCommand._cppr_registry['header']:
            menu_commands = possible_command.get_commands(detail)

            if menu_commands:

                if after_one:
                    output.append({ 'caption' : '-' })
                else:
                    after_one = True

                for menu_option in menu_commands:
                    command_name, *menu_data = menu_option

                    to_open = possible_command.default_open
                    if len(menu_data) > 1:
                        to_open, menu_data = menu_data
                    else:
                        menu_data = menu_data[0]

                    menu_data.update({
                        "subcommand" : _BaseCppCommand.subl_command_name(possible_command),
                        "default_open" : to_open,
                        "header_file" : header,
                        "source_file" : source
                    })
                    output.append(
                        { "command" : "cpp_refactor",
                          "caption" : command_name,
                          "args" : {
                            "data" : menu_data
                        } }
                    )

        return output


    def on_post_text_command(self, view, command, args):
        if command == "context_menu":
            utils._write_menu([])


    def on_text_command(self, view, command, args):
        if command != "context_menu":
            return
    
        #
        # Before we do anything, let's assert which file we're in and
        # that we have the oposite file present and accounted for
        #

        current_file = view.file_name()
        if not current_file:
            return # Nothing to be done

        header_or_source = None
        other_file = None

        base, filetype = os.path.splitext(current_file)
        if filetype in ('.h', '.hpp'):
            header_or_source = 'header'
            if os.path.isfile(base + '.cpp'):
                other_file = base + '.cpp'

        elif filetype in ('.cpp',):
            header_or_source = 'source'

            if os.path.isfile(base + '.h'):
                other_file = base + '.h'
            elif os.path.isfile(base + '.hpp'):
                other_file = base + '.hpp'

        if header_or_source is None or other_file is None:
            return # This isn't a C++ file

        #
        # The process of building our menu is most of the battle because
        # we need to do all of the searching and data mining before developing
        # a useful
        #

        context_menu = []

        vec = self._args_to_vec(args)
        pos = view.window_to_layout(vec)

        if header_or_source == 'header':
            context_menu.extend(self._build_header_menu(
                view, command, args, pos, current_file, other_file
            ))

        if context_menu:
            utils._write_menu([{
                "caption" : "C++ Toolkit",
                "children" : context_menu
            }])

