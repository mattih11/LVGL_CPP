# LVGL_CPP
Automatic CPP binding generator for LVGL

## Preliminaries
Some assumptions are made on the LVGL base source code that we are using
to create a auto-generated CPP-binding for LVGL

### Naming Convention
In LVGL we can see a typical pattern in file names and general structure of the LVGL project,
such as function names, "classes" and their corresponding functionality

#### Classes
Classes are generated in the following manner:
- A file lv_{CLASSNAME}.h exists
##### Functions
- all non-static member functions are written in the following way:
lv_{CLASSNAME}_{FUNCTIONAME}(lv_{BASENAME|CLASSNAME}_t *, ...)
- static class functions are written like this:
lv_{CLASSNAME}_{FUNCTIONAME}(...), where the first parameter is different to:
lv_{BASENAME|CLASSNAME}_t

##### Inheritance
{BASECLASS} is a parent/base of {CLASSNAME} if:
a function lv_create_{CLASSNAME} exists in lv_{CLASSNAME}.h and has a pointer-return type that is not:
{CLASSNAME} *, then the return type {BASECLASS} * is used to determine the base class.
