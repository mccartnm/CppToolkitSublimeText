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
from .cpp_refactor_commands import CppTokenizer, _BaseCppCommand
from .cpp_refactor_commands import CppRefactorDetails, FunctionState

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

    def _current_line(self, view, pos):
        """
        Find the current line data. This is important because we have
        to handle search back until we find a proper delimiter
        :return: str
        """

        og_pos = pos[:]
        current_line = self._context_line(view, pos)

        og_pos = self._previous_line(view, og_pos)
        done = False
        while og_pos[1] > 0 and not done:
            # Back up until we find the right item
            prev_line = self._context_line(view, og_pos)

            # Check if the previous line is a comment
            if prev_line.strip().startswith('//'):
                done = True
                break

            # Strip away anything after a line comment
            if '//' in prev_line:
                prev_line = prev_line[:prev_line.index('//')]

            rev_line = prev_line[::-1]

            # Check if the line ends in a multiline comment (it's backwards)
            if rev_line.startswith('/*') or rev_line.startswith(':'):
                og_pos = self._next_line(view, og_pos) # Too far
                done = True
                break

            create_line = ''
            should_prepend = True
            should_prev = True
            in_quotes = False

            for i, char in enumerate(rev_line):

                if char == '"':
                    in_quotes ^= 1 # Invert

                if (not in_quotes) and (char == '/') and (i + 1 < len(rev_line) and rev_line[i+1] == '/'):
                    should_prepend = False # This is a line comment, no coming back from this.
                    done = True
                    break

                if char in (' ', '\n', '\t') or (char not in CppTokenizer.DELIMITS):
                    create_line = char + create_line
                else:
                    # We've hit a delimit!
                    og_pos = self._next_line(view, og_pos)
                    should_prev = False
                    done = True
                    break

            if should_prepend:
                current_line = create_line + current_line

            if should_prev:
                og_pos = self._previous_line(view, og_pos)

        fs = FunctionState.from_position(view, og_pos)
        return (fs.found(), og_pos)


    def _build_header_menu(self, view, command, args, pos, header, source):
        """
        Using the _BaseCppCommand registry of header-capable commands, we build a dynamic
        context menu that can act on the text we're setting out on.
        :param pos: tuple(float, float) of the position we're in
        :param header: Path to the header file
        :param source: Path to the source file
        :return: list
        """
        original_position = pos[:]

        output = []

        current_word = view.substr(view.word(view.layout_to_text(pos)))

        current_line, mark_pos = self._current_line(view, pos)
        after_one = False

        detail = CppRefactorDetails(
            view=view,
            command=command,
            args=args,
            pos=pos,
            current_file_type='header_file',
            current_word=current_word,
            current_line=current_line,
            header=header,
            source=source,
            marked_position=mark_pos
        )

        for possible_command in _BaseCppCommand._cppr_registry['header']:
            menu_commands = possible_command.get_commands(detail)

            if menu_commands:

                if after_one:
                    output.append({ 'caption' : '-' })
                else:
                    after_one = True

                for menu_option in menu_commands:
                    hotkey_name, command_name, *menu_data = menu_option

                    to_open = possible_command.default_open
                    if len(menu_data) > 1:
                        to_open, menu_data = menu_data
                    else:
                        menu_data = menu_data[0]

                    menu_data.update({
                        "subcommand" : _BaseCppCommand.subl_command_name(possible_command),
                        "default_open" : to_open,
                        "header_file" : header,
                        "source_file" : source,
                        'detail' : detail.to_json() # Might as well have it all
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
        """
        When finished with a text command, we want to erase the menu
        we created to assert we always start fresh
        :param view: sublime.View
        :param command: str of sublime command
        :param args: additional args passed by sublime
        :return: None
        """
        if command == "context_menu":
            utils._write_menu([])


    def on_text_command(self, view, command, args):
        """
        Text commands are handled when interacting with a view.

        This will attempt to locate any options currently available
        based on the users context and build a context menu accordingly.

        :param view: sublime.View
        :param command: str of sublime command
        :param args: additional args passed by sublime
        :return: None
        """
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

        settings = sublime.load_settings('CppToolkit.sublime-settings')

        base, filetype = os.path.splitext(current_file)

        filetype = filetype.replace('.', '', 1)

        header_types = settings.get("header_file_types", ["h", "hpp"])
        source_types = settings.get("source_file_types", ["cpp"])

        if filetype in header_types:
            header_or_source = 'header'
            for source_type in source_types:
                if os.path.isfile(base + '.' + source_type):
                    other_file = base + '.' + source_type
                    break

        elif filetype in source_types:
            header_or_source = 'source'

            for header_type in header_types:
                if os.path.isfile(base + '.' + header_type):
                    other_file = base + '.' + header_type
                    break

        if header_or_source is None or other_file is None:
            return # This isn't a C++ file

        #
        # The process of building our menu is most of the battle because
        # we need to do all of the searching and data mining before actually
        # giving the user the menu. This means we need to be quick and quiet
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

