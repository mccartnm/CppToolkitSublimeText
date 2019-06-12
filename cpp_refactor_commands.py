"""
The commands that actually write and move data provided by our "data"
"""

import re
import os
import json
import sublime
import sublime_plugin


class CppTokenizer(object):
    """
    Utility for building tokens of C++ files. This is by no means complete
    but forgoes a lot of the nitty gritty to be lean and fast 
    """
    DELIMITS = ( '*', '=', '{', '}', '\'', '\"', '(', ')', ';', ':', ' ', '\n', '\t' )

    def __init__(self, view, start, end):
        self._view = view
        self._current = start
        self._end = end - self._view.line_height()
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

    HEADER_FUNCTION = re.compile(
        r'(\s+)?(?P<static_or_virtual>static|virtual)?(\s+)(?P<type>[^\s]+)(\s)?'\
        r'(?P<method>[^\s\(]+)((\s+)?\()+?(?P<args>[^\;]+)?'\
        r'((\s+)?\))+?(\s+)?(?P<addendum>[^\;]+)?'
    )

    FUNC_PRIV = re.compile(r'(\s+)?(?P<priv>.+)\:$')

    DECLARE_FORMAT = "{type} {ownership}{method}({source_arguments}){classifiers}"

    @classmethod
    def get_commands(cls, view, command, args, pos, current_line, header, source):
        """
        Check to see if this is a header function of some sort
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
            "ownership_chain" : chain,
            "function_priv" : func_priv
        })

        return [match_data]


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
        """
        local_data = data.copy()

        # -- Ownership path (if any)
        local_data['ownership'] = self._build_ownership(data['ownership_chain'])

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
        self.view.insert(edit, self.view.size(), '\n\n' + decl + '\n{\n    \n}\n')

        end_size = self.view.size()
        row, col = self.view.rowcol(end_size)

        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.view.text_point(row - 2, 4)))
        self.view.show_at_center(end_size)


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

