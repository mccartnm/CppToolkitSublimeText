Cpp Toolkit
===========
A collection of utilities for managing C++ code implementation.

# Capabilities

## Auto Implement
Many IDEs out there make use their inherent understanding of you project through syntax and preprocessing to present perks like being able to automatically declare methods from the header within the source. This save the developer _loads_ of time.

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

### The Catch
Ultimately, this tool is parsing the file and doing the best job it can but, as any C++ developer knows, the language has quite a few caveats so you may not get the perfect signature or ownership every time however it should still get you moving in the right direction.

# Install
Using Package Control [Sublime Package Manager](http://wbond.net/sublime_packages/package_control)

To install use these commands.

* Hit `Ctrl + Shift + P`
* Type `install` and select `Package Control: Install Package`
* Type `CppToolkit` and select `CppToolkit`


