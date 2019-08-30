#include "host.h"
#include "mbed.h"
#include "QRScanner.h"

QRScanner qrscanner(D5, D1, D0);
// buffer to store external scans
static char qrbuf[1000];

static void (*data_callback)(const char * data) = NULL;

void host_request_data(void (*callback)(const char * data)){
	data_callback = callback;
	qrscanner.trigger = 0;
}

void host_update(){
    if(qrscanner.getStatus() == QR_EXTERNAL){
    	qrscanner.trigger = 1;
    	data_callback(qrbuf);
    	printf("QR data scanned: %s\r\n", qrbuf);
    	memset(qrbuf, 0, sizeof(qrbuf));
		qrscanner.setBuffer(qrbuf, sizeof(qrbuf));
    }
}

void host_init(){
	memset(qrbuf, 0, 1000);
	qrscanner.setBuffer(qrbuf, sizeof(qrbuf));
}