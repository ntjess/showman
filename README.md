# Showman

![](./showman.jpg)

------------------------------------------------------------------------

Automagic tools to smooth the package documentation & development
process.

- Package your files for local typst installation or PR submission in
  one command

- Provide your readme in typst format with code block examples, and let
  `showman` do the rest! In one command, it will the readme to markdown
  and render code block outputs as included images.

  - Bonues points – let `showman` know your repository path and it will
    ensure images will properly appear in your readme even after your
    package has been distributed through typst’s registry.

## Installation

**Prerequisites**: Make sure you have `typst` and `pandoc` available
from the command line. Then, in a python virtual environment, run:

``` bash
git clone https://github.com/ntjess/showman.git
cd showman
pip install -e .
# Optional:
# showman package typst.toml
```

The optional last step lets you import `showman` it in your code with

``` typ
#import "@local/showman:0.1.0"
```

After enough people test this package, I will submit it as an official
typst package and it will be directly available as a `@preview` citizen.

## Usage

### Converting your readme to markdown

Create a typst file with ```` ```example ```` code blocks that show the
output you want to include in your readme. For instance:

``` typst
#import "@preview/cetz:0.1.2"

= Hello, world!
Let's do something complicated:

#cetz.canvas({
  import cetz.plot
  import cetz.palette
  cetz.draw.set-style(axes: (tick: (length: -.05)))
  // Plot something
  plot.plot(size: (3,3), x-tick-step: 1, axis-style: "left", {
      for i in range(0, 3) {
      plot.add(domain: (-4, 2),
      x => calc.exp(-(calc.pow(x + i, 2))),
      fill: true, style: palette.tango)
    }
  })
})
```
![Example 1](assets/example-1.png)

Then, run the following command:

``` bash
showman md <path-to-typst-file>
```

Congrats, you now have a readme with inline images 🎉

You can optionally specify your workspace root, output file name, image
folder, etc. These options are visible under `showman md --help`.

**Note**: You can customize the appearance of these images by providing
`showman` the template to use when creating them. In your file to be
rendered, create a variable called `showman-config` at the outermost
scope:

``` typ
// Render images with a black background and red text
#let showman-config = (
  template: it => {
    set text(fill: red)
    rect(fill: black, it)
  }
)
```

Behind the scenes, showman imports your file as a module and looks for
this variable. If it is found, your template and a few other options are
injected into the example rendering process.

**Note**: If every example has the same setup (package imports, etc.),
and you don’t want the text to be included in your examples, you can
pass `eval-kwargs` in this config as well to specify a string that gets
prefixed to every example. Alternatively, pass variables in a scope
directly:

``` typ
// Setup either through providing scope or import prefixes
#let my-variable = 5
#let showman-config = (
  eval-kwargs: (
    prefix: "#import \"@preview/cetz:0.1.2\"
  ),
  // Now you can use `my-var` in your examples
  scope: (my-var: my-variable)
)
```

### Caveats

- `showman` uses the beautiful `pandoc` to do most of the markdown
  conversion heavy lifting. So, if your document can’t be processed by
  pandoc, you may need to adjust your syntax until pandoc is happy
  making a markdown document.

- Typst doesn’t allow page styling inside containers. Since `showman`
  must use containers to extract each rendered example, you can’t use
  `#set page(...)` or `#pagebreak()` inside your examples.

## Publishing your package

You’ve done the hard work of creating a beautiful, well-documented
manual. Now it’s time to share it with the world. `showman` can help you
package your files for distribution in one command, after some minimal
setup.

1.  Make sure you have a `typst.toml` file that follows typst [packaging
    guidelines](https://github.com/typst/packages)

2.  Add a new block to your toml file as follows:

``` toml
[tool.packager]
paths = [...]
```

Where `paths` is a list of files and directories you want to include in
your package.

3.  Run the following command from the root of your repository:

``` bash
showman package <path-to-toml-file>
```

4.  Without any other arguments, you’ve just installed your package in
    your system’s local typst packages folder. Now you can import it
    with `typst #import "@local/mypackage:<version>"`.

    - You can alternatively specify the path to your fork of
      `typst/packages` to prep your files for a PR, or specify a
      `--namespace` other than `local`.

**Note**: You can see the full list of command options with
`showman package --help`.