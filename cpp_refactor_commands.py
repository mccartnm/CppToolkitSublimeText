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
from .lib.utils import CppTokenizer, CppRefactorDetails
from .lib.utils import _BaseCppRefactorMeta, FunctionState 

class _BaseCppCommand(sublime_plugin.TextCommand, metaclass=_BaseCppRefactorMeta):
    """
    Root class that all context aware commands are registered under to build
    the proper menu and items based on "where" the user is.

    ..code::python
        class MyCommand(_BaseCppCommand):

            # Bitwise flags to tell CppToolkit when this command should
            # be tested for commands to run.
            flags = _BaseCppCommand.IN_HEADER | _BaseCppCommand.IN_SOURCE

            @classmethod
            def get_commands(cls, detail):
                # .. Overload here to return a list of commands in the format of:
                return [ [
                    '<unique_id>',
                    '<verbose_name>',
                    'source_file|header_file',
                    dict(command_information)
                ], ... ]

            def run(self, edit, **data):
                # .. Oveload to process command. data is the
                # dict(command_information) above.

    ..note::

        The .get_commands() is run on any right click that matches the ``flags``
        so be careful when introducing any heavy logic.
    """
    flags = 0

    default_open = 'source_file'

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


class InteralInsertCommand(sublime_plugin.TextCommand):
    """
    Quick insert command for running on different views. Quick and dirty.
    """

    @classmethod
    def fire(cls, view, data):
        while view.is_loading():
            time.sleep(0.1)
        command_name = _BaseCppCommand.subl_command_name(InteralInsertCommand)
        view.run_command(command_name, data)


    def run(self, edit, **data):
        full_body = data['full_body']
        point = data['point'] or self.view.size()
        self.view.window().focus_view(self.view)
        self.view.insert(edit, point, full_body)
        location = point + (len(full_body) - 3)
        row, col = self.view.rowcol(location)

        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.view.text_point(row, col)))
        self.view.show_at_center(location)



# ----------------------------------------------------------------------------
# -- Text Commands

class CppDeclareInSourceCommand(_BaseCppCommand):
    """
    A command for implementing methods where required.

    This command supports a few distinct actions.

    - Implement in Source
    - Implement outside of Scope
    - Move implementation to Source
    - Move implementation outside of scope
    - Copy impl signature to clipboard

    This command can (mostly) pull appart a function delared in a given scope
    using the FunctionState and some internal hueristics. The biggest
    challenge is the shear number of caveats in the C++ language. Nothing a
    whole log of if statements won't solve I suppose.
    """

    flags = _BaseCppCommand.IN_HEADER # | _BaseCppCommand.IN_SOURCE <- eventually

    #
    # The basic implementation format string
    #
    DECLARE_FORMAT = "{type}{ownership}{method}({source_arguments}){classifiers}"

    @classmethod
    def get_commands(cls, detail):
        """
        Check to see if this is a header function of some sort
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
            "function_priv" : func_priv,
            'original_position' : original_position
        })

        commands = []

        if fs.has_impl:

            #
            # Present the functions to move the implementation
            #

            move_source = deepcopy(match_data)
            move_source.update({ 'in_' : 'header', 'move_to' : 'source_file' })

            move_header = deepcopy(match_data)
            move_header.update({ 'in_' : 'header', 'move_to': 'header_file' })

            commands = [
                ["move_impl_to_source",
                 "Move Implementation To {}".format(os.path.basename(detail.source)),
                 detail.current_file_type,
                 move_source],
                ["move_impl_outside_class",
                 "Move Implementation Outside Class",
                 detail.current_file_type,
                 move_header]
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
                ['delc_in_source',
                 "Declare In {}".format(os.path.basename(detail.source)),
                 'source_file',
                 source_declare],
                # This works in the header_file
                ['delc_in_header',
                 "Declare In {}".format(os.path.basename(detail.header)),
                 'header_file',
                 header_declare],
            ]

        copy_declare = deepcopy(match_data)
        copy_declare.update({ 'in_' : 'clipboard' })
        commands.append(
            ['copy_delc',
             'Copy Declaration to Clipboard',
             'header_file',
             copy_declare]
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


    def _clean_impl(self, impl):
        """
        Dedent and make sure we've closed the scopes
        :param impl: Raw implementation string we usually get from the FunctionState
        :return: str 
        """
        import textwrap
        return '{' + textwrap.indent(textwrap.dedent(impl[1:-1]), '    ') + '}'


    def _impl_to_regex(self, impl):
        """
        To find the implementation as it exists, we inject whitespace finding utilites
        to find it however it's written in sublime
        """
        output = ''
        ws_finder = r'((\s)+)?'
        items = impl.split('\n')
        for i, line in enumerate(items):
            output += ws_finder + re.escape(line.strip())
            if i != (len(items) - 1):
                output += ws_finder
        return output


    def build_delc(self, data):
        """
        Given data, construct the signature based on ownership as well as
        clean up the types for default values, handling the additional
        classifiers (virtual, static, const, etc)

        :param data: The data containing various settings passed by the
        get_commands() above
        :return: tuple(signature_string, data copy that's been manipulated)
        """
        local_data = data.copy()

        # -- Ownership path (if any)
        local_data['ownership'] = self._build_ownership(
            local_data['ownership_chain']
        )

        # -- Check for const and pointer/references
        if local_data.get('is_const'):
            local_data['type'] = 'const ' + local_data['type']

        if local_data.get('encap'):
            local_data['type'] += local_data['encap']

        method = local_data.get('method')
        if method.startswith('*') or method.startswith('&'):
            point, method = method[0], method[1:]
            local_data['type'] = local_data['type'] + ' ' + point
            local_data['method'] = method
        else:
            local_data['type'] += ' '

        # -- Source Arguments
        if local_data['args'] is None:
            local_data['source_arguments'] = ''
        else:
            source_arguments = []
            for arg in local_data['args'].split(','):
                trimmed = arg.strip()
                if "=" in trimmed:
                    # Clean away default vales
                    trimmed = trimmed.split('=')[0].strip()
                source_arguments.append(trimmed)

            local_data['source_arguments'] = ', '.join(source_arguments)

        # -- Additional Classifiers
        local_data['classifiers'] = ''
        if local_data['addendum'] is not None:
            if 'const' in local_data['addendum']:
                local_data['classifiers'] += ' const'

        decl = CppDeclareInSourceCommand.DECLARE_FORMAT.format(**local_data)
        return (decl, local_data)


    def run(self, edit, **data):
        """
        Construct the complete function signature, handling the implementation
        as requested, and spawn a worker to do the actual manip. We use this in
        the event that we have to move to another file to do the last bits of
        work (e.g. move commands need to remove the impl to "place" it elsewhere)
        """
        decl, local_data = self.build_delc(data)

        if local_data['in_'] in ['header', 'source']:

            impl_string = '\n{\n    \n}\n'
            if local_data.get('impl'):
                impl_string = '\n' + self._clean_impl(local_data['impl'])

            full_body = '\n\n' + decl + impl_string;

            # __import__('pprint').pprint(local_data)
            if local_data.get('impl'):
                # If we have the impl, we need to move it!
                f = self._impl_to_regex(impl_string)
                region = self.view.find(
                    self._impl_to_regex(impl_string),
                    self.view.layout_to_text(local_data['detail']['marked_position'])
                )
                self.view.replace(edit, region, ';')

            if local_data['in_'] == 'source':
                # For the time being, we declare at the end of the source file
                point = self.view.size()

            else:

                # We attempt to declare just outside the highest ownership scope
                point = None
                if local_data['ownership_chain']:
                    point = CppTokenizer.location_outside(self.view, local_data['ownership_chain'][0])
                
                if point is None:
                    point = self.view.size()

            insert_data = {
                'full_body' : full_body,
                'point' : point
            }

            edit_view = self.view
            window = self.view.window()

            move_info = local_data.get('move_to')
            if move_info and (move_info != local_data['detail']['current_file_type']):

                insert_data['point'] = None

                # We have to switch to the other file
                if local_data['detail']['current_file_type'] == 'header_file':
                    edit_file = local_data['detail']['source']
                else:
                    edit_file = local_data['detail']['header']
                edit_view = window.find_open_file(edit_file)

                if edit_view is None:
                    edit_vieww = window.open_file(edit_file)

            #
            # Fire off another thread to make sure we have a loaded buffer
            #
            b_thread = threading.Thread(
                target=InteralInsertCommand.fire,
                args=(edit_view, insert_data)
            )
            b_thread.start()

        else:
            #
            # A simple copy action
            #
            impl_string = '\n{\n}\n'
            if data.get('impl'):
                impl_string = '\n' + data['impl']

            full_body = decl + impl_string;
            sublime.set_clipboard(full_body)


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
            ['gen_getset',
             'Generate Getter/Setter',
             'header_file',
             match_data],
            ['gen_getset_w_impl',
             'Generate Getter/Setter (With Implementation)',
             'header_file',
             with_imply]
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
        a_thread.start() # Cleanup? - hopefully gc'll handle it
