Sticky notes are easy with `colorful-boxes`:

```example
#import "@preview/colorful-boxes:1.2.0" as boxes

#boxes.stickybox(width: 1in)[
  Hello world!
]
```

conchord makes it easy to add new chords, both for diagrams and lyrics. Unlike chordx, you don't need to think about layout and pass lots of arrays for drawing barres. Just pass a string with holded frets and it will work:

```example
#import "@preview/conchord:0.1.0": new-chordgen, overchord

#let chord = new-chordgen()

#box(chord("x32010", name: "C"))
#box(chord("x33222", name: "F#m/C#"))
#box(chord("x,9,7,8,9,9"))
```


To use this library through the Typst package manager (for Typst v0.6.0+), write for example `#import "@preview/tablex:0.0.7": tablex, cellx` at the top of your Typst file (you may also add whichever other functions you use from the library to that import list!).

Here's an example of what tablex can do:

```example
#import "@preview/tablex:0.0.7": tablex, rowspanx, colspanx

#tablex(
  columns: 4,
  align: center + horizon,
  auto-vlines: false,

  // indicate the first two rows are the header
  // (in case we need to eventually
  // enable repeating the header across pages)
  header-rows: 2,

  // color the last column's cells
  // based on the written number
  map-cells: cell => {
    if cell.x == 3 and cell.y > 1 {
      cell.content = {
        let value = int(cell.content.text)
        let text-color = if value < 10 {
          red.lighten(30%)
        } else if value < 15 {
          yellow.darken(13%)
        } else {
          green
        }
        set text(text-color)
        strong(cell.content)
      }
    }
    cell
  },

  /* --- header --- */
  rowspanx(2)[*Username*], colspanx(2)[*Data*], (), rowspanx(2)[*Score*],
  (),                 [*Location*], [*Height*], (),
  /* -------------- */

  [John], [Second St.], [180 cm], [5],
  [Wally], [Third Av.], [160 cm], [10],
  [Jason], [Some St.], [150 cm], [15],
  [Robert], [123 Av.], [190 cm], [20],
  [Other], [Unknown St.], [170 cm], [25],
)
```