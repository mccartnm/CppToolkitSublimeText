"""
The commands that actually write and move data provided by our "data"
"""

import re
import os
import json
import sublime
import sublime_plugin

from copy import deepcopy

class CppTokenizer(object):
    """
    Utility for building tokens of C++ files. This is by no means complete
    but forgoes a lot of the nitty gritty to be lean and fast 
    """
    DELIMITS = ( '*', '=', '{', '}', '\'', '\"', '(', ')', ';', ':', ' ', '\n', '\t' )

    def __init__(self, view, start=0, end=None, use_line=None):
        self._view = view
        self._current = start
        if end:
            self._end = end - self._view.line_height()
        else:
            self._end = self._view.layout_extent()[1]
        self._use_line = use_line
        self._current_tokens = None


    def _context_line(self, pos: (int, float)):
        """
        Get the line of text from our current view based on a position
        """
        return self._view.substr(self._view.line(self._view.layout_to_text((0, pos))))        


    def _get_tokens(self, line: str) -> list:
        """
        Search for additional items to break up our tokens by
        """
        tokens = []
        current = ''

        previous = None
        line = line.strip()
        spin = 0

        for i, char in enumerate(line):
            if spin > 0:
                spin -= 1
                continue

            if char == '*' and previous == '/':
                # -- multi-line comment
                tokens.append('/*')
                continue

            if char == '*' and (i + 1 < len(line)) and line[i+1] == '/':
                tokens.append('*/')
                spin = 1
                continue

            if char not in CppTokenizer.DELIMITS:
                current += char
            else:
                if current:
                    tokens.append(current)
                current = ''
                if char not in (' ', '\n', '\t'):
                    tokens.append(char)
            previous = char

        if current:
            tokens.append(current)

        return tokens


    def next(self, **kwargs):
        """
        Rather than host the whole buffer in one shot, we just get a
        line at a time and keep requesting it until we're done
        """

        # Grab a token list
        while (self._current_tokens in (None, [])):

            if self._use_line is not None:
                self._current_tokens = self._get_tokens(self._use_line)
            else:
                if self._current > self._end:
                    # We've made it where we wanted to go
                    self._current_tokens = None
                    return None

                toks = self._get_tokens(self._context_line(self._current).strip())
                self._current += self._view.line_height()
                if toks:
                    self._current_tokens = toks
                    break

        # The active token awaits!
        current_token = self._current_tokens.pop(0)

        if kwargs.get('in_comment'):
            return current_token # comments don't validate

        if current_token in ('', ' '):
            return self.next() # Keep going

        # Basic Validation
        if current_token.startswith('//'):
            # Line comment, skip the rest of the line
            self.skip_line()
            return self.next()

        if current_token.startswith('/*'):
            # We have a inner comment, just
            # spin until we're out of tokens or
            # we hit the other side of the comment
            while True:
                tok = self.next(in_comment=True)
                if tok is None:
                    return None

                if tok.endswith('*/'):
                    # We've hit the end of the comment so whatever comes
                    # next should be the right bit
                    return self.next()

        return current_token

    def current_point(self):
        """
        :return: sublime point that dictates where in the file we are
        """
        # FIXME: Need a better understanding of X column
        return self._view.layout_to_text((10000, self._current))

    def skip_line(self):
        """
        Pass on the rest of our current tokens
        """
        self._current_tokens = None


    def spin_until(self, char):
        while True:
            token = self.next()
            if token is None:
                return

            if char in token:
                return

    @classmethod
    def ownership_chain(cls, view, at_location):
        """
        Build the ownership chain of the currently selected item by
        identifying the scope we fall into
        :return: list[list[str(class|struct|namespace), str]]
        """
        proc_tokens = ( 'class', 'struct', 'namespace' )
        izer = cls(view, 0, at_location[1])

        chain = []
        active_proc = []

        while True:
            token = izer.next()
            if token is None:
                # Nothing left
                break

            if token in proc_tokens:

                if active_proc:
                    chain.append(active_proc)

                active_proc = [token, None]
                while True:
                    #
                    # Find the proc name
                    #
                    inner_tok = izer.next()
                    if inner_tok is None or inner_tok.endswith(';'):
                        #
                        # We've hit the EOF or a forward declaration,
                        # let's skip this all together
                        #
                        active_proc[1] = None
                        break;

                    if inner_tok == '{':
                        #
                        # We should have found it
                        #
                        break

                    if inner_tok == ':':
                        #
                        # We have to spin the token until we get to a scope
                        # opener or a terminator
                        #
                        while True:
                            lower_tok = izer.next()
                            if lower_tok is None:
                                active_proc[1] = None
                                failed = True
                                break

                            if '{' in lower_tok or ';' in lower_tok:
                                # We've found the opening to the class
                                # and we can let the rest of the process
                                # take place
                                break
                        break

                    active_proc = [token, inner_tok]

                if active_proc[1] is None:
                    # We don't have a class defined
                    if chain:
                        active_proc = chain.pop()
                    else:
                        active_proc = []

            elif '}' in token:
                #
                # We're at the end of a proc scope
                #
                if chain:
                    active_proc = chain.pop()
                else:
                    active_proc = []

            elif token == '{':
                #
                # The start of a scope that isn't tied to a proc
                #
                izer.spin_until('}')

        return (chain + ([active_proc] if active_proc else []))


    @classmethod
    def location_outside(cls, view, root_ownership):
        """
        :return: point - location outside of the ending scope of our class, struct,
        or namespace
        """
        izer = cls(view)

        found_proc = False
        scope_count = 0

        while True:
            token = izer.next()
            if token is None:
                break # Nothing left

            if not found_proc and token == root_ownership[0]:
                #
                # We have the right type, now we just need to check if we have the
                # right name
                #
                while True:
                    inner_tok = izer.next()
                    if inner_tok is None or inner_tok.endswith(';'):
                        found_proc = False
                        break # Not the right one

                    if inner_tok == root_ownership[1]:
                        #
                        # We have the proc name, but we still have to make sure
                        # this isn't a forward declare
                        #
                        found_proc = True

                    if inner_tok == '{':
                        #
                        # If, by this point, we have found the item, it means
                        # we're in it's scope, we now just work until we exit
                        # said scope
                        #
                        # However if we haven't found the item, it means we're
                        # looking at another item
                        #
                        break

            if found_proc:
                #
                # Now that we know about our type, we need to keep moving until
                # we find the end of it's scope
                #
                if token == '{':
                    scope_count += 1
                if token == '}':
                    if scope_count == 0:
                        # We've made it!
                        if root_ownership[0] != 'namespace':
                            izer.spin_until(';') # Get passed the terminator
                        return izer.current_point()
                    else:
                        scope_count -= 1

        # We couldn't find the end of that scope
        return None


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
    def get_commands(cls, view, command, args, pos, current_line, header, source):
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
    def get_commands(cls, view, command, args, pos, current_line, header, source):
        """
        Check to see if this is a header function of some sort
        TODO: Use the tokenizer to parse the file rather than the regex mess
        """
        match = cls.HEADER_FUNCTION.match(current_line)
        if not match:
            return None

        original_position = pos[:]
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
            "current_line" : current_line,
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
            ["Declare In {}".format(os.path.basename(source)), 'source_file', source_declare],
            # This works in the header_file
            ["Declare In {}".format(os.path.basename(header)), 'header_file', header_declare],
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
                if data['ownership_chain']:
                    point = CppTokenizer.location_outside(self.view, data['ownership_chain'][0])
                else:
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

