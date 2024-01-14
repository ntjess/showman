#import "@preview/showman:0.1.0": runner, formatter

#show raw: it => {
  let kwargs = if it.block {
    (width: 100%)
  } else {
    (inline: true)  
  }
  formatter.format-raw(it, ..kwargs)

}
#show <example-output>: formatter.format-raw

#let cache = json("/.coderunner.json").at("examples/external-code.typ", default: (:))
#let show-rule = runner.external-code.with(result-cache: cache, direction: ttb)

// These show rules only add style; they aren't necessary to generate outputs
#show raw.where(lang: "python"): show-rule
#show raw.where(lang: "bash"): show-rule
#show raw.where(lang: "cpp"): show-rule

The outputs for each language will be visible after running
```
showman execute ./examples/external-code.typ
```
*Note*: If you're on Windows, the `bash` example will not evaluate.

```python
import functools

@functools.lru_cache(maxsize=None)
def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)

print(fib(30))
```

```cpp
#include <iostream>
#include <vector>

int fib(int n, std::vector<int> &cache) {
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
    std::vector<int> cache(101, -1);
    std::cout << fib(30, cache) << std::endl;
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