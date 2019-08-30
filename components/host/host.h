#ifndef __HOST_H__
#define __HOST_H__

void host_init();
void host_update();
void host_request_data(void (*callback)(const char * data));

#endif