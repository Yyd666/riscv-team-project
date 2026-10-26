#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) uint64_t kernel(const uint64_t *values, uint64_t count) {
    uint64_t total = 0;
    for (uint64_t i = 0; i < count; ++i) total += values[i];
    return total;
}

int main(void) {
    uint64_t n = 0, values[32] = {0};
    if (scanf("%llu", (unsigned long long *)&n) != 1 || n > 32) return 2;
    for (uint64_t i = 0; i < n; ++i) if (scanf("%llu", (unsigned long long *)&values[i]) != 1) return 2;
    printf("%llu\n", (unsigned long long)kernel(values, n));
    return 0;
}
