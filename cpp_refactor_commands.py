"""
The commands that actually write and move data provided by our "data"
"""

import re
import os
import json
import sublime
import sublime_plugin

from copy import deepcopy
from .lib.utils import CppTokenizer

class CppRefactorDetails(object):
    """
    Class handling the large amount of information surrouding our context aware
    commands. This is passed to the get_commands(...) function of the concrete
    _BaseCppCommand(s)
    """
    def __init__(self, **kwargs):
        self._view = kwargs.get('view')
        self._command = kwargs.get('command')
        self._args = kwargs.get('args')
        self._pos = kwargs.get('pos')
        self._current_word = kwargs.get('current_word')
        self._current_line = kwargs.get('current_line')
        self._header = kwargs.get('header')
        self._source = kwargs.get('source')
        self._current_file_type = kwargs.get('current_file_type')

    @property
    def view(self):
        return self._view

    @property
    def command(self):
        return self._command

    @property
    def args(self):
        return self._args

    @property
    def pos(self):
        return self._pos

    @property
    def current_word(self):
        return self._current_word

    @property
    def current_line(self):
        return self._current_line

    @property
    def header(self):
        return self._header

    @property
    def source(self):
        return self._source

    @property
    def current_file_type(self):
        return self._current_file_type
    


class _BaseCppRefactorMeta(type):
    """
    Registry class for any commands that we want to be utilized in the menus and
    hotky actions.
    """
    def __init__(cls, name, bases, dct):
        """
        Construct the class
        """
        if not hasattr(cls, '_cppr_registry'):
            cls._cppr_registry = {
                'source' : [],
                'header' : []
            }
        else:
            if cls.flags & _BaseCppCommand.IN_HEADER:
                cls._cppr_registry['header'].append(cls)
            if cls.flags & _BaseCppCommand.IN_SOURCE:
                cls._cppr_registry['source'].append(cls)


class _BaseCppCommand(sublime_plugin.TextCommand, metaclass=_BaseCppRefactorMeta):
    """
    Root command that all cpp children are registered under to build the proper
    menu and items
    """
    IN_HEADER = 0x0000001
    IN_SOURCE = 0x0000010
    flags = 0

    default_open = 'source_file'

    hotkey = None # __FUTURE__

    @classmethod
    def context_line(cls, view, pos):
        return view.substr(view.line(view.layout_to_text(pos)))

    @classmethod
    def previous_line(cls, view, pos):
        return (pos[0], pos[1] - view.line_height())

    @classmethod
    def next_line(cls, view, pos):
        return (pos[0], pos[1] + view.line_height())

    @staticmethod
    def subl_command_name(cls):
        regex = re.compile(r'(.+?)([A-Z])')
        def _snake(match):
            return match.group(1).lower() + '_' + match.group(2).lower()
        return re.sub(regex, _snake, cls.__name__.replace("Command", ''), 0)

    @classmethod
    def get_commands(cls, detail):
        pass


# ----------------------------------------------------------------------------
# -- Text Commands

class CppDeclareInSourceCommand(_BaseCppCommand):
    """
    The text comand that is run to declare a method from our header file within
    our source
    """

    # This is a header only function
    flags = _BaseCppCommand.IN_HEADER

    # FIXME: This has a finite limitation on templating, we need to handle this
    # better. Probably with the tokenizer and some deeper parsing
    HEADER_FUNCTION = re.compile(
        r'(\s+)?(?P<static_or_virtual>static|virtual)?(\s+)?'\
        r'(?P<is_const>const)?(\s)?(?P<type>[^\s]+)(\s)?'\
        r'(?P<encap>\<(?:(?:\<(?:(?:\<(?:[^<>])*\>)|(?:[^<>]))*\>)|(?:[^<>]))*\>)?(\s)'\
        r'(?P<method>[^\s\(]+)((\s+)?\()+?(?P<args>[^\;]+)?'\
        r'((\s+)?\))+?(\s+)?(?P<addendum>[^\;]+)?'
    )

    FUNC_PRIV = re.compile(r'(\s+)?(?P<priv>.+)\:$')

    DECLARE_FORMAT = "{type}{ownership}{method}({source_arguments}){classifiers}"

    @classmethod
    def get_commands(cls, detail):
        """
        Check to see if this is a header function of some sort
        TODO: Use the tokenizer to parse the file rather than the regex mess
        """
        view = detail.view
        match = cls.HEADER_FUNCTION.match(detail.current_line)
        if not match:
            return None

        original_position = detail.pos[:]
        chain = CppTokenizer.ownership_chain(view, original_position)

        func_priv = 'default' # public, private, protected, etc (future use)

        this_position = cls.previous_line(view, original_position)
        while this_position[1] > 0:
            search_line = cls.context_line(view, this_position)
            this_position = (this_position[0], this_position[1] - view.line_height())
            priv_match = cls.FUNC_PRIV.match(search_line)

            if priv_match and func_priv == 'default':
                # This should the privilege of the function within it's class
                func_priv = priv_match.groupdict()['priv']
                break

            search_line = cls.previous_line(view, this_position)

        match_data = match.groupdict()
        match_data.update({
            "current_line" : detail.current_line,
            "ownership_chain" : chain,
            "function_priv" : func_priv
        })

        source_declare = deepcopy(match_data)
        source_declare.update({ 'in_' : 'source' })

        header_declare = deepcopy(match_data)
        header_declare.update({ 'in_' : 'header' })

        copy_declare = deepcopy(match_data)
        copy_declare.update({ 'in_' : 'clipboard' })

        return [
            ["Declare In {}".format(os.path.basename(detail.source)), 'source_file', source_declare],
            # This works in the header_file
            ["Declare In {}".format(os.path.basename(detail.header)), 'header_file', header_declare],
            ["Copy Declaration to Clipboard", 'header_file', copy_declare]
        ]


    def _build_ownership(self, chain):
        """
        :retur: str of the ownership chain
        """
        output = '::'.join([c[1] for c in chain])
        if output:
            output += '::'
        return output

    def run(self, edit, **data):
        """
        Build the source declaration and place it into the source file
        TODO: Use the tokenizer to parse the file rather than all this hand holding
        """
        local_data = data.copy()

        # -- Ownership path (if any)
        local_data['ownership'] = self._build_ownership(data['ownership_chain'])

        # -- Check for const and pointer/references
        if data.get('is_const'):
            local_data['type'] = 'const ' + local_data['type']

        if data.get('encap'):
            local_data['type'] += data['encap']

        method = data.get('method')
        if method.startswith('*') or method.startswith('&'):
            point, method = method[0], method[1:]
            local_data['type'] = local_data['type'] + ' ' + point
            local_data['method'] = method
        else:
            local_data['type'] += ' '

        # -- Source Arguments
        if data['args'] is None:
            local_data['source_arguments'] = ''
        else:
            source_arguments = []
            for arg in data['args'].split(','):
                trimmed = arg.strip()
                if "=" in trimmed:
                    # Clean away default vales
                    trimmed = trimmed.split('=')[0].strip()
                source_arguments.append(trimmed)

            local_data['source_arguments'] = ', '.join(source_arguments)

        # -- Additional Classifiers
        local_data['classifiers'] = ''
        if data['addendum'] is not None:
            if 'const' in data['addendum']:
                local_data['classifiers'] += ' const'

        decl = CppDeclareInSourceCommand.DECLARE_FORMAT.format(**local_data)

        if data['in_'] in ['header', 'source']:
            full_boddy = '\n\n' + decl + '\n{\n    \n}\n';

            if data['in_'] == 'source':
                # For the time being, we declare at the end of the source file
                point = self.view.size()

            else:

                # We attempt to declare just outside the highest ownership scope
                point = None
                if data['ownership_chain']:
                    point = CppTokenizer.location_outside(self.view, data['ownership_chain'][0])
                
                if point is None:
                    point = self.view.size()

            self.view.insert(edit, point, full_boddy)
            location = point + (len(full_boddy) - 3)
            row, col = self.view.rowcol(location)

            self.view.sel().clear()
            self.view.sel().add(sublime.Region(self.view.text_point(row, col)))
            self.view.show_at_center(location)

        else:
            full_boddy = decl + '\n{\n}\n';
            sublime.set_clipboard(full_boddy)


# ----------------------------------------------------------------------------
# -- Winow Commands

class CppRefactorCommand(sublime_plugin.WindowCommand):
    """
    This window command is actually called by all commands and just
    reroutes to the text command when needed. This makes menu building
    more straight forward when jumping back and forth between header and
    source
    """
    def run(self, data):
        """
        Based on the command passed, let's handle the 
        """
        show_file = data[data['default_open']]
        show_view = self.window.find_open_file(show_file)

        if show_view is None:
            show_view = self.window.open_file(show_file)

        self.window.focus_view(show_view)

        show_view.run_command(data['subcommand'], data)

