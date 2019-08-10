

import re
import os
import json
from contextlib import contextmanager

def _cache_path():
    import sublime
    return os.path.join(sublime.cache_path(), "CppRefactor")


def _write_menu(menu):
    import sublime
    menu_path = os.path.join(_cache_path(), "Context.sublime-menu")
    with open(menu_path, "w+") as cache:
        cache.write(json.dumps(menu, cache))

class CppTokenizer(object):
    """
    Utility for building tokens of C++ files. This is by no means complete
    but forgoes a lot of the nitty gritty to be lean and fast 
    """
    DELIMITS = ( '*', '=', '<', '>', '{', '}', '\'', '\"', '(', ')', ';', ':', ' ', '\n', '\t' )

    def __init__(self, view, start=0, end=None, use_line=None):
        self._view = view
        self._current = start
        if end:
            self._end = end - self._view.line_height()
        elif self._view:
            self._end = self._view.layout_extent()[1]
        self._use_line = use_line
        self._current_tokens = None
        self._skip_whitespace = True


    def __iter__(self):
        return self

    def __next__(self):
        d = self._next()
        if d is not None:
            return d
        else:
            raise StopIteration

    @contextmanager
    def include_white_space(self):
        self._skip_whitespace = False
        yield
        self._skip_whitespace = True

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
                if self._skip_whitespace:
                    if char not in ('\n', '\t'):
                        tokens.append(char)
                else:
                    tokens.append(char)
            previous = char

        if current:
            tokens.append(current)

        return tokens


    def _next(self, **kwargs):
        """
        Rather than host the whole buffer in one shot, we just get a
        line at a time and keep requesting it until we're done
        """
        # Grab a token list
        while (self._current_tokens in (None, [])):

            if hasattr(self, '_no_more'):
                return None

            if self._use_line is not None:
                self._current_tokens = self._get_tokens(self._use_line)
                self._use_line = None # nomnom!
                self._no_more = True
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

        if current_token in ('', ' ') and self._skip_whitespace:
            return self._next() # Keep going

        # Basic Validation
        if current_token.startswith('//'):
            # Line comment, skip the rest of the line
            self.skip_line()
            return self._next()

        if current_token.startswith('/*'):
            # We have a inner comment, just
            # spin until we're out of tokens or
            # we hit the other side of the comment
            while True:
                tok = self._next(in_comment=True)
                if tok is None:
                    return None

                if tok.endswith('*/'):
                    # We've hit the end of the comment so whatever comes
                    # next should be the right bit
                    return self._next()

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
            token = self._next()
            if token is None:
                return

            if char in token:
                return

    def spin_scope(self):
        scope_count = 0
        while True:
            token = self._next()
            if token is None:
                return

            if token == '{':
                scope_count += 1
            elif token == '}':
                if scope_count:
                    scope_count -= 1
                else:
                    return
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

        token = None
        while True:
            previous = token
            token = izer._next()
            if token is None:
                # Nothing left
                break

            if token in proc_tokens and previous != 'using':

                if active_proc:
                    chain.append(active_proc)

                active_proc = [token, None]
                inner_tok = None
                while True:
                    #
                    # Find the proc name
                    #
                    prev_tok = inner_tok
                    inner_tok = izer._next()
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
                            lower_tok = izer._next()
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

                    #
                    # Edge case for 'final' decl
                    #
                    if inner_tok == 'final':
                        inner_tok = prev_tok

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
                izer.spin_scope()

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
            token = izer._next()
            if token is None:
                break # Nothing left

            if not found_proc and token == root_ownership[0]:
                #
                # We have the right type, now we just need to check if we have the
                # right name
                #
                while True:
                    inner_tok = izer._next()
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