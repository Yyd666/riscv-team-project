#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *digits, uint32_t count) {
    uint32_t value = 0;
    for (uint32_t i = 0; i < count; ++i) value = (value * 10 + digits[i]) % 1000003;
    return value;
}

int main(void) {
    uint32_t n = 0, digits[32] = {0};
    if (scanf("%u", &n) != 1 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%u", &digits[i]) != 1 || digits[i] > 9) return 2;
    printf("%u\n", kernel(digits, n));
    return 0;
}
