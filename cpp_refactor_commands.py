"""
The commands that actually write and move data provided by our "data"
"""

import re
import os
import time
import json
import sublime
import threading
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

    # hotkey = None # __FUTURE__

    FUNC_PRIV = re.compile(r'(\s+)?(?P<priv>.+)\:$')

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

class FunctionState(object):
    """
    Utility object for handling the building of our functions
    for various state control
    """

    class Container:

        opposites = {
            '{' : '}',
            '[' : ']',
            '<' : '>',
            '(' : ')'
        }

        def __init__(self):
            self.char = None
            self.count = 0

        @property
        def valid(self):
            return self.char is not None

        def is_close(self, other):
            return self.opposites[self.char] == other


    # -- Lookup States
    STATIC_OR_VIRTUAL = 0x0000001
    IS_CONST          = 0x0000010
    TYPE              = 0x0000100
    NAME              = 0x0001000
    ARGS              = 0x0010000
    ADDENDUM          = 0x0100000
    IMPL              = 0x1000000

    def __init__(self):
        self._static_or_virtual = None
        self._is_const_result = False
        self._type = []
        self._type_and_name = []
        self._args = []
        self._addendum = None
        self._impl = None

        self._valid = False
        self._container = self.Container()

        self._lookup_state = self.STATIC_OR_VIRTUAL
        self._complete_string = ''


    @property
    def valid(self):
        return self._valid


    @property
    def has_impl(self):
        return self._impl is not None


    def _resolve(self, token):
        """
        Given a token and the information gathered so far,
        
        We move through states based on what should proceed one item
        after another.

        :param token: The token that we're looking to utilize
        """
        if self._lookup_state == self.STATIC_OR_VIRTUAL:
            if token in ('', ' '):
                return True

            self._lookup_state = self.IS_CONST
            if token in ('static', 'virtual'):
                self._static_or_virtual = token
                return True # Vital! We comsumed this!

        if self._lookup_state == self.IS_CONST:
            if token in ('', ' '):
                return True

            self._lookup_state = self.TYPE
            if token == ('const'):
                self._is_const_result = True
                return True # Consumed!

        if self._lookup_state == self.TYPE:

            # When we enter the type lookup, this is the
            # first time we might have multiple tokens to consume

            # Check for encapsulation
            if token in ('<', '('):
                if not self._container.valid:
                    self._container.char = token
                    self._container.count = 1
                elif self._container.char == token:
                    self._container.count += 1

            if self._container.valid and self._container.is_close(token):
                self._container.count -= 1
                if self._container.count <= 0:
                    # Terminus
                    self._container.char = None

            if not self._container.valid and token in ('const', '{', ';', '='):

                #
                # We're out of scope should have reached the end of the type,
                # name, and args. Because of this, we now have to filter
                # backwards to find the name and args, splitting them from
                # the type
                #
                scope_count = 0
                first_scope = True
                rem_count = 0

                for rev_token in self._type_and_name[::-1]:
                    rem_count += 1

                    if first_scope and rev_token == ' ':
                        continue

                    if rev_token == ')': # Remember, we're in reverse
                        if scope_count >= 1:
                            self._args.append(rev_token)

                        first_scope = False
                        scope_count += 1

                    elif rev_token == '(':
                        scope_count -= 1
                        if scope_count >= 1:
                            self._args.append(rev_token)

                    elif scope_count >= 1:
                        self._args.append(rev_token)

                    elif scope_count == 0:
                        self._name = rev_token
                        self._valid = True # If we've made it here, we should be good
                        break

                self._args = self._args[::-1] # Went in backwards
                self._type = ''.join(self._type_and_name[:-rem_count])

                #
                # Make sure we take care of the terminal token.
                #
                if token == 'const':
                    self._addendum = 'const'

                elif token == '{':
                    self._container.char = token
                    self._container.count = 1
                    self._impl = token
                    self._lookup_state = self.IMPL

                elif token == ';':
                    self._complete_string += token
                    return False

            else:
                self._type_and_name.append(token)

        elif self._lookup_state == self.IMPL:
            if not self._container.valid:
                return False # We're out of the implementation

            if token == '{':
                self._container.count += 1

            if token == '}':
                self._container.count -= 1

            if self._container.count <= 0:
                # We've terminates
                self._impl += token
                self._container.char = None
            else:
                self._impl += token

        return True


    def to_dict(self):
        return {
            'static_or_virtual' : self._static_or_virtual,
            'is_const'          : self._is_const_result,
            'type'              : self._type.strip(),
            'method'            : self._name.strip(),
            'args'              : ''.join(self._args),
            'addendum'          : self._addendum,
            'impl'              : self._impl
        }


    def found(self):
        return self._complete_string


    @classmethod
    def from_text(cls, view, text):
        state = FunctionState()

        izer = CppTokenizer(view, use_line=text)
        with izer.include_white_space():
            for token in izer:
                if not state._resolve(token):
                    break # We've hit the end of our function
                state._complete_string += token

        return state

    @classmethod
    def from_position(cls, view, position):
        state = FunctionState()

        izer = CppTokenizer(view, start=position[1] + 1)
        with izer.include_white_space():
            for token in izer:
                if not state._resolve(token):
                    break
                state._complete_string += token

        return state


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
        r'((\s+)?\))+?(\s+)?(?P<addendum>[^\;|\{]+)?(?P<impl>\{)?'
    )

    DECLARE_FORMAT = "{type}{ownership}{method}({source_arguments}){classifiers}"

    @classmethod
    def get_commands(cls, detail):
        """
        Check to see if this is a header function of some sort
        TODO: Use the tokenizer to parse the file rather than the regex mess
        """
        view = detail.view

        fs = FunctionState.from_text(view, detail.current_line)

        if not fs.valid:
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

        match_data = fs.to_dict()
        match_data.update({
            "current_line" : detail.current_line,
            "ownership_chain" : chain,
            "function_priv" : func_priv
        })

        commands = []

        if fs.has_impl:

            #
            # Present the functions to move the implementation
            #

            move_source = deepcopy(match_data)
            move_source.update({ 'in_' : 'header', 'move_to' : 'source' })

            move_header = deepcopy(match_data)
            move_header.update({ 'in_' : 'header', 'move_to': 'header' })

            commands = [
                ["Move Implementation To {}".format(os.path.basename(detail.source)), 'header_file', move_source],
                ["Move Implementation Outside Class", 'header_file', move_header]
            ]

        else:

            #
            # Functions to initially declare the impl
            #

            source_declare = deepcopy(match_data)
            source_declare.update({ 'in_' : 'source' })

            header_declare = deepcopy(match_data)
            header_declare.update({ 'in_' : 'header' })
            commands = [
                ["Declare In {}".format(os.path.basename(detail.source)), 'source_file', source_declare],
                # This works in the header_file
                ["Declare In {}".format(os.path.basename(detail.header)), 'header_file', header_declare],
            ]

        copy_declare = deepcopy(match_data)
        copy_declare.update({ 'in_' : 'clipboard' })
        commands.append(
            ["Copy Declaration to Clipboard", 'header_file', copy_declare]
        )

        return commands


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
            impl_string = '\n{\n    \n}\n'
            if data.get('impl'):
                impl_string = '\n' + data['impl']

            full_boddy = '\n\n' + decl + impl_string;

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
            impl_string = '\n{\n}\n'
            if data.get('impl'):
                impl_string = '\n' + data['impl']

            full_boddy = decl + impl_string;
            sublime.set_clipboard(full_boddy)


class CppGetterSetterFunctionsCommand(_BaseCppCommand):
    """
    Quick way of building the setter and getter for a given member
    """
    flags = _BaseCppCommand.IN_HEADER # | _BaseCppCommand.IN_SOURCE

    WITH_DEFAULT = re.compile(
        r'(?:\s+)?(?P<type>.+)(?:\s)(?P<member>[^\s;]+)'\
        r'(?:\s+)?(\=)(\s+)?(?P<default>.+)?\;'
    )

    NO_DEFAULT = re.compile(
        r'(?:\s+)?(?P<type>.+)(?:\s)(?P<member>[^\s;]+)(?:\s+)?\;'
    )

    GETTER_FORMAT = '\n{indent}{classifier}{type} {p_or_r}get{property_upper}() const{get_ending}'
    SETTER_FORMAT = '\n{indent}void set{property_upper}({set_classifier}{type} {p_or_r}{property_name}){set_ending}'

    def get_const_types(self):
        settings = sublime.load_settings('CppToolkit.sublime-settings')
        return list(settings.get('non_const_types', ['float', 'double', 'int']))

    @classmethod
    def get_commands(cls, detail):
        """
        Getting the commands...
        """
        view = detail.view
        func_priv = 'default'
        func_priv_line = None
        func_priv_loc = (0, 0)
        this_position = cls.previous_line(view, detail.pos)

        original_ownership = CppTokenizer.ownership_chain(view, detail.pos)

        while this_position[1] > 0:
            search_line = cls.context_line(view, this_position)
            this_position = (this_position[0], this_position[1] - view.line_height())
            priv_match = cls.FUNC_PRIV.match(search_line)

            if priv_match and func_priv == 'default':

                # Make sure we're within the right owner
                this_ownership = CppTokenizer.ownership_chain(view, this_position)

                if len(original_ownership) != len(this_ownership):
                    continue

                fail = False
                for i in range(len(this_ownership)):
                    if original_ownership[i] != this_ownership[i]:
                        fail = True
                        break

                if fail:
                    continue

                # This should the privilege of the function within it's class
                func_priv = priv_match.groupdict()['priv']
                func_priv_loc = this_position
                func_priv_line = search_line
                break

        match = cls.WITH_DEFAULT.match(detail.current_line)
        if match is None:
            match = cls.NO_DEFAULT.match(detail.current_line)

        if match is None:
            return [] # Not a member we can devine

        match_data = match.groupdict()
        match_data.update({
            'current_line' : detail.current_line,
            'original_position': detail.pos,
            'func_priv' : func_priv,
            'func_priv_loc' : func_priv_loc,
            'func_priv_line': func_priv_line,
        })

        with_imply = deepcopy(match_data)
        with_imply.update({ 'impl' : True })

        return [
            ['Generate Getter/Setter', 'header_file', match_data],
            ['Generate Getter/Setter (With Implementation)', 'header_file', with_imply]
        ]


    def run(self, edit, **data):
        """
        Create the functions and then build them into the header
        """

        member_name = data['member']
        if not member_name:
            return # Nothing to do

        type_ = data['type']
        if member_name[0] in ('&', '*'):
            type_ += member_name[0]
            member_name = member_name[1:]

        property_name = member_name
        if member_name.startswith('m_'):
            property_name = member_name[2:]

        local_data = data.copy()

        local_data['member'] = member_name
        local_data['property_name'] = property_name
        local_data['property_upper'] = property_name[0].upper() + property_name[1:]

        # Stacked basic types don't make no sense to be const
        if type_ in self.get_const_types():
            local_data['classifier'] = ''
            local_data['set_classifier'] = ''
            local_data['p_or_r'] = ''
        else:
            local_data['classifier'] = 'const '
            local_data['set_classifier'] = 'const '

        if data['func_priv'] != 'default':
            local_data['indent'] = ' ' * (data['func_priv_line'].index(data['func_priv']) + 4)
        else:
            local_data['indent'] = '    '

        if data.get('impl'):
            local_data['get_ending'] = ' { return ' + member_name + '; }'
            local_data['set_ending'] = ' { ' + member_name + ' = ' + property_name + '; }'
        else:
            local_data['get_ending'] = ';'
            local_data['set_ending'] = ';'

        #
        # Kruft to handle the delicate matter of pointers and references
        # to make sure they are consistent
        #
        if local_data.get('p_or_r') is None:
            if type_[-1] in ('&', '*'):
                local_data['p_or_r'] = type_[-1]
                type_ = type_[:-1]
                local_data['set_classifier'] = ''
            else:
                local_data['p_or_r'] = '&'

        local_data['type'] = type_
        getter = self.GETTER_FORMAT.format(**local_data)
        setter = self.SETTER_FORMAT.format(**local_data)

        loc = data['func_priv_loc']
        if loc == [0, 0]:
            loc = self.previous_line(self.view, data['original_position'])
        else:
            loc = self.next_line(self.view, loc)
        point = self.view.layout_to_text(loc)

        self.view.insert(edit, point, getter + setter)


# ----------------------------------------------------------------------------
# -- Winow Commands

class CppRefactorCommand(sublime_plugin.WindowCommand):
    """
    This window command is actually called by all commands and just
    reroutes to the text command when needed. This makes menu building
    more straight forward when jumping back and forth between header and
    source
    """

    def _fire_command(self, view, data):
        while view.is_loading():
            time.sleep(0.01)
        view.run_command(data['subcommand'], data)

    def run(self, data):
        """
        Based on the command passed, let's handle the 
        """
        show_file = data[data['default_open']]
        show_view = self.window.find_open_file(show_file)

        if show_view is None:
            show_view = self.window.open_file(show_file)

        self.window.focus_view(show_view)
        
        # This is async in the event that we need to wait for
        # the view to load (which happens on another thread)
        a_thread = threading.Thread(
            target=self._fire_command,
            args=(show_view, data)
        )
        a_thread.start() # Cleanup?
