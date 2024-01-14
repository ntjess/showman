#import "@local/showman:0.1.0": formatter

#set page(height: auto)
#show: formatter.template.with(
  eval-kwargs: (
    direction: ltr
  )
)

#include("simple.typ")