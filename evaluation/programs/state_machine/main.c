#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *events, uint32_t count) {
    uint32_t state = 0;
    for (uint32_t i = 0; i < count; ++i) {
        if (events[i] == 0) state = (state + 1) % 4;
        else if (events[i] == 1) state = (state + 3) % 4;
        else if (events[i] == 2) state = (state * 2 + 1) % 4;
    }
    return state;
}

int main(void) {
    uint32_t n = 0, events[32] = {0};
    if (scanf("%u", &n) != 1 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%u", &events[i]) != 1) return 2;
    printf("%u\n", kernel(events, n));
    return 0;
}
