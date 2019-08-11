"""
Metaclass utilities for the CppToolkit
"""

class _BaseCppRefactorMeta(type):
    """
    Registry class for any commands that we want to be utilized in the menus and
    hotky actions.

    This dynamically attributes the classes to the right header/source
    functionality
    """
    IN_HEADER = 0x0000001
    IN_SOURCE = 0x0000010

    def __init__(cls, name, bases, dct):
        """
        Construct the class
        """
        if not hasattr(cls, '_cppr_registry'):
            cls.IN_HEADER = _BaseCppRefactorMeta.IN_HEADER
            cls.IN_SOURCE = _BaseCppRefactorMeta.IN_SOURCE
            cls._cppr_registry = {
                'source' : [],
                'header' : []
            }
        else:
            if cls.flags & _BaseCppRefactorMeta.IN_HEADER:
                cls._cppr_registry['header'].append(cls)
            if cls.flags & _BaseCppRefactorMeta.IN_SOURCE:
                cls._cppr_registry['source'].append(cls)