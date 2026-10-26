#include <stdio.h>
#include <stdint.h>

static int32_t lookup(int32_t value) {
    switch (value) { case 0: return 3; case 1: return 5; case 2: return 7; default: return -1; }
}

__attribute__((noinline)) int32_t kernel(const int32_t *values, uint32_t count) {
    int32_t total = 0;
    for (uint32_t i = 0; i < count; ++i) total += lookup(values[i]);
    return total;
}

int main(void) {
    uint32_t n = 0; int32_t values[32] = {0};
    if (scanf("%u", &n) != 1 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%d", &values[i]) != 1) return 2;
    printf("%d\n", kernel(values, n));
    return 0;
}
