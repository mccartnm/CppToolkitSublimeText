import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from lib.utils import CppTokenizer

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


    @property
    def valid(self):
        return self._valid
    

    def _resolve(self, token):
        """
        Given a token and the information gathered so far,
        
        We move through states based on what should proceed one item
        after another.

        :param token: The token that we're looking to utilize
        """
        if self._lookup_state == self.STATIC_OR_VIRTUAL:
            if token in ('', ' '):
                return

            self._lookup_state = self.IS_CONST
            if token in ('static', 'virtual'):
                self._static_or_virtual = token
                return # Vital! We comsumed this!

        if self._lookup_state == self.IS_CONST:
            if token in ('', ' '):
                return

            self._lookup_state = self.TYPE
            if token == ('const'):
                self._is_const_result = True
                return # Consumed!

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
                found_scope = False

                for rev_token in self._type_and_name[::-1]:
                    rem_count += 1

                    if first_scope and (rev_token == ' ' or rev_token.isalnum()):
                        continue

                    if rev_token == '=':
                        found_scope = False

                    if rev_token == ')': # Remember, we're in reverse
                        found_scope = True
                        if scope_count >= 1:
                            self._args.append(rev_token)

                        first_scope = False
                        scope_count += 1

                    elif rev_token == '(':
                        found_scope = True
                        scope_count -= 1
                        if scope_count >= 1:
                            self._args.append(rev_token)

                    elif scope_count >= 1:
                        self._args.append(rev_token)

                    elif scope_count == 0:
                        self._name = rev_token
                        self._valid = found_scope # If we've made it here, we should be good
                        break

                self._args = self._args[::-1] # Went in backwards
                self._type = ''.join(self._type_and_name[:-rem_count])

                #
                # Make sure we take care of the terminal token.
                #
                if token == 'const':
                    self._addendum = 'const'

                if token == '{':
                    self._container.char = token
                    self._container.count = 1
                    self._impl = token
                    self._lookup_state = self.IMPL

            else:
                self._type_and_name.append(token)

        elif self._lookup_state == self.IMPL:
            if not self._container.valid:
                return

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


    @classmethod
    def from_text(cls, view, text):
        state = FunctionState()

        izer = CppTokenizer(view, use_line=text)
        with izer.include_white_space():
            for token in izer:
                state._resolve(token)

        __import__('pprint').pprint(state.to_dict())
        print (state.valid)
        return state

function_string = "std::string type() const override;"
# function_string = 'virtual foo<bar<baz, std::function<void(const QString &)>>> my_foo(QString blarg = "faz", foo<bar(kattt)> ok);'

fs = FunctionState.from_text(None, function_string)

# f = """{
#     heelp.clean();
#     my grod = foo.bar();
#     {
#         "okay";
#     }
# }
# """

# import re

# output = ''
# ws_finder = r'((\s)+)?'
# for line in f.split('\n'):

#     trim = line.strip()
#     output += ws_finder + re.escape(trim) + ws_finder


# print (output)

# print (re.match(output, f))
