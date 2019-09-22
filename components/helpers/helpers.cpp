#include "helpers.h"
#include <stdio.h>
#include "alert.h"

/** small helper functions that prints 
 *  data in hex to the serial port */
void print_hex(const uint8_t * data, size_t data_len){
    for(int i=0; i<data_len; i++){
        printf("%02x", data[i]);
    }
}

/** just adds a new line to the end of the data */
void println_hex(const uint8_t * data, size_t data_len){
    print_hex(data, data_len);
    printf("\r\n");
}

/** prints error, in colors! */
void show_err(const char * message){
	printf("\033[1;31m");
    printf("ERROR: %s\r\n", message);
	printf("\033[0m");
    gui_alert_create("ERROR!", message, "Ok");
}

/** logs in cyan */
void logit(const char * module, const char * message){
	printf("\033[1;36m");
	printf("[%s]\033[0;36m %s\r\n", module, message);
	printf("\033[0m");
}