#ifndef __HELPERS_H__
#define __HELPERS_H__

#include <stdint.h>
#include <string.h>

void print_hex(const uint8_t * data, size_t data_len);
void println_hex(const uint8_t * data, size_t data_len);
void show_err(const char * message);

void logit(const char * module, const char * message);

#endif