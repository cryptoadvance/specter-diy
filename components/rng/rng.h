#ifndef RNG_H
#define RNG_H

#include "mbed.h"

/** initializes TRNG */
int rng_init();

/** generates a single random number */
uint32_t rng_get_random_number(void);

/** fills the buffer with random data */
size_t rng_get_random_buffer(uint8_t * arr, size_t len);


#endif