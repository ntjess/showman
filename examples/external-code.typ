#import "@preview/showman:0.1.0": runner, formatter
#set page(height: auto)

#show raw: it => {
  let kwargs = if it.block {
    (width: 100%, line-numbers: true)
  } else {
    (inline: true)
  }
  formatter.format-raw(it, ..kwargs)

}

#show <example-output>: formatter.format-raw
// #show <example-input>: formatter.format-raw

#let cache = json("/.coderunner.json").at("examples/external-code.typ", default: (:))
#let show-rule = runner.external-code.with(
  result-cache: cache,
  direction: ttb,
)


= A mini rosseta code example: Fibonacci numbers
The outputs for each language will be visible after running
```bash
showman execute ./examples/external-code.typ
```
- *Note*: If you're on Windows, the `bash` example will not evaluate.
- `typst` will render for free, independent of `showman execute`.

#show raw: it => {
  heading(it.lang)
  if it.lang != "typst" {
    show-rule(it)
  } else {
    runner.standalone-example(it, direction: ttb)
  }
}


```typst
#let fib(n) = {
  if n < 2 {
    n
  } else {
    // Typst memoizes by default :)
    fib(n - 1) + fib(n - 2)
  }
}
#fib(50)
``` 

```python
import functools

@functools.lru_cache(maxsize=None)
def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)

fib(50)
```

```cpp
#include <iostream>
#include <vector>
typedef unsigned long long ulong;
ulong fib(ulong n, std::vector<ulong> &cache) {
    if (n < 2) {
        return n;
    }
    if (cache[n] != -1) {
        return cache[n];
    }
    cache[n] = fib(n-1, cache) + fib(n-2, cache);
    return cache[n];
}

int main() {
    std::vector<ulong> cache(101, -1);
    std::cout << fib(50, cache) << std::endl;
    return 0;
}
```

```bash
fib() {
    local n=$1
    if [ $n -lt 2 ]; then
        echo $n
        return
    fi
    local a=$(fib $((n-1)))
    local b=$(fib $((n-2)))
    echo $((a+b))
}
# Not memoized, so use a much smaller number
fib 10
```
