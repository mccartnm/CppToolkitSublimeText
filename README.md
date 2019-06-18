Cpp Toolkit
===========
A collection of utilities for managing C++ code implementation.

> Disclamer: Sublime is not a fully featured C++ IDE and this plugin doesn't try to make it one. It simply tries to speed up your usual work

# Capabilities

## Auto Implement
Many IDEs out there make use their inherent understanding of you project through syntax and preprocessing to present perks like being able to automatically declare methods from the header within the source. This save the developer _loads_ of time.

![Usability](/img/header_a.jpg?raw=true)

## Getter / Setter Functions
Getters and setters are used in a plentiful sense in modern C++. For this reason, there is also the ability to right click on members and build their respective functions.

Currently this does its best to identify the proper signature but may not always be what you're looking for. That said it should still speed up Sublime typing.

![GetAndSet](/img/header_c.jpg?raw=true)

## A Scenario
Let's say you have the header:
```cpp
// my_file.h
namespace my_namespace
{

class MyClass : public SomeBase
{
public:
    // ...

    void getSomeData(float bar, MyStruct::SomeEnum val = MyStruct::Value) const override;
}
```
And now you want to move that to your source. Currently in Sublime you have a limited set of options. Until this plugin I would do the following:

1. Move my cursor to the line and hit `Ctrl + C` to copy the whole line
    * If the definition was multiple lines, I would use `Ctrl + L` enough time to get it all or use my mouse
2. Swap to the source with `Alt + O`
3. Move my cursor to where I could declare the method
4. Paste in the header code via `Ctrl + V`
5. Highlight the line (or just have one cursor on it if one line) and `Shift + Tab` enough to set it
6. Fill in the ownership chain
7. Die a little inside
8. Go throughout the function and remove any cruft like `override;` and the `= MyStrcut::Value` in the example above
9. Finally add the parentheses and get to freaking work

### The Fix
With `Cpp Toolkit`, the workflow is:

1. Right click on the function name to declare
2. Go to `C++ Toolkit > Declare in <source_file_name>.cpp`

And bam! You'll be moved to the source file, all the right guts and ownership will be filled in, no pesky non-const classifiers or default values, and your cursor will be right where you need it to start typing the function body!

> Note: At the moment, this assumes, just like the `Alt + O` shortcut, that the header and implentation are next to each other in the filesystem. In the future I may add ways to declare an implementation root or location or some such.

### The Catch
Ultimately, this tool is parsing the file and doing what it can with immediate information but, as any C++ developer knows, the language has quite a few caveats so you may not get the perfect signature or ownership every time however it should still get you moving in the right direction and speed up _a lot_ of typing.


# Install
Using Package Control [Sublime Package Manager](http://wbond.net/sublime_packages/package_control)

To install use these commands (once it's up on the Sublime Package Repository).

* Hit `Ctrl + Shift + P`
* Type `install` and select `Package Control: Install Package`
* Type `CppToolkit` and select `CppToolkit`

# Roadmap
There are many things to do for this plugin that I'm hoping to tick away at in my spare time

1. _Basic_ preprocess for things like `#ifdef 0 ... #endif` clauses
2. ~~Camel case/Snake case conversion when needed~~ This is already in the sweet [CaseConversion](https://github.com/jdavisclark/CaseConversion) plugin
3. Switch statement breakout (based on some kind of classifier)
4. Smart inject based on other declarations in the source rather than always at the end
5. Reverse implement to go from source to header under a given privilege
6. Apply changes to function signatures in both header and source
7. ~~Getter/Setter functions of members~~ (done)
8. Have the commands work in both source and header, just using the parser to understand what commands can be used
9. Hotkeys for select functions