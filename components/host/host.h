#ifndef __HOST_H__
#define __HOST_H__

#include <string.h>
#include <stdint.h>

#define HOST_DEFAULT			0 // drops data if not set to listen
#define HOST_LISTEN_ONCE		1 // set to receive data once, will be cleared after one packet
#define HOST_ALWAYS_LISTEN		2 // set to receive data even if it's not triggered by the main logic
#define HOST_ALLOW_SEND			4 // set if data should be sent to host

void host_init(int flags, float timeout);
void host_request_data();
void host_update();
int host_data_available();
int host_send(uint8_t * data, size_t len);
void host_flush();
size_t host_read(uint8_t * buf, size_t len);
uint8_t * host_get_data();

#endif