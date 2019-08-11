"""
Utility for details when creating context aware commands
"""

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
        self._marked_position = kwargs.get('marked_position')

    def to_json(self):
        """
        :return: dict mapping of our properties (no view) for storage in the
        context menu or other setting-passing
        """
        return {
            'command' : self.command,
            'args' : self.args,
            'pos' : self.pos,
            'current_word' : self.current_word,
            'current_line' : self.current_line,
            'header' : self.header,
            'source' : self.source,
            'current_file_type' : self.current_file_type,
            'marked_position' : self.marked_position
        }


    @property
    def marked_position(self):
        """
        :return: The position that we think is most likely the start of a given item
        """
        return self._marked_position
    

    @property
    def view(self):
        """
        :return: sublime.View instance we initiallize the
        _BaseCppCommand.get_commands from
        """
        return self._view

    @property
    def command(self):
        """
        :return: The sublime command being processed (e.g. 'context_menu')
        """
        return self._command

    @property
    def args(self):
        """
        :return: The arguments supplied to the sublime command
        """
        return self._args

    @property
    def pos(self):
        """
        :return: tuple(x, y) that we initiated the command at
        """
        return self._pos

    @property
    def current_word(self):
        """
        :return: The word that we've selected while building the command
        """
        return self._current_word

    @property
    def current_line(self):
        """
        :return: The "line" that we've selected while building the command.
        This should be the full scope of a function if it can be found.
        """
        return self._current_line

    @property
    def header(self):
        """
        :return: The absolute path to the header file (if any)
        """
        return self._header

    @property
    def source(self):
        """
        :return: The absolute path to the source file (if any)
        """
        return self._source

    @property
    def current_file_type(self):
        """
        :returb: The active file (source|header) that we're running the
        command in
        """
        return self._current_file_type