"""
CppToolkit
"""


from .tokenize import CppTokenizer

class FunctionState(object):
    """
    Utility object for handling the parsing of methods. This abstracts some of
    the nitty-gritty of where a function starts and ends.
    """

    class Container:
        """
        Simple controller for scope spinning in the function state.
        """
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
            """
            :return: True if we're within a scope
            """
            return self.char is not None

        def is_close(self, other):
            """
            :param other: A token that we're testing for equality
            :return: True if other is the "opposite" of our active scope
            """
            if not self.valid:
                return False
            return self.opposites[self.char] == other


    # -- Lookup States
    # This is to help us know what kind of characters to consume.
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
        """
        :return: True if a name and type have been defined.
        Everything else is just addon content.
        """
        return self._valid


    @property
    def has_impl(self):
        """
        :return: True if we have constructed an implementation
        """
        return self._impl is not None


    def _resolve(self, token):
        """
        Given a token and the information gathered so far,
        
        We move through states based on what should proceed one item
        after another.

        :param token: The token that we're looking to utilize
        :return: bool if the iteration should consume additional tokens
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
                found_scope = False

                for rev_token in self._type_and_name[::-1]:
                    rem_count += 1

                    if first_scope and rev_token == ' ':
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

                elif token == '{':
                    self._container.char = token
                    self._container.count = 1
                    self._impl = token + '\n'
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
                # We've terminated
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


    def _from_tokenizer(self, izer):
        """
        """        
        with izer.include_white_space():
            for token in izer:
                if not self._resolve(token):
                    break # We've hit the end of our function

                if self._lookup_state == self.IMPL:
                    izer.temp_no_trim()

                self._complete_string += token

    @classmethod
    def from_text(cls, view, text):
        state = FunctionState()
        izer = CppTokenizer(view, use_line=text)
        state._from_tokenizer(izer)
        return state

    @classmethod
    def from_position(cls, view, position):
        state = FunctionState()
        izer = CppTokenizer(view, start=position[1] + 1)
        state._from_tokenizer(izer)
        return state