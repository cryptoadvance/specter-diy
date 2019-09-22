#include "host.h"
#include "specter_config.h"
#include "mbed.h"
#include "QRScanner.h"
#include "helpers.h"

static unsigned int host_flags = HOST_DEFAULT;

Timer t;
static float tmax;

QRScanner qrscanner(D5, D1, D0);
// buffer to store external scans
static char * qrbuf = NULL;

void host_update(){
    if(qrscanner.getStatus() == QR_EXTERNAL){
        t.stop();
        t.reset();
    	qrscanner.trigger = 1;
        host_flags = host_flags & 0xE; // meh
    }else{
        if(host_flags & HOST_LISTEN_ONCE){
            float dt = t.read();
            if(dt > tmax){
                t.stop();
                t.reset();
                show_err("QR scanner timed out, try again.");
            }
        }
    }
}

void host_init(int flags, float timeout){
    qrbuf = (char *)calloc(SPECTER_HOST_INPUT_SIZE, 1);
    host_flags = flags;
    memset(qrbuf, 0, SPECTER_HOST_INPUT_SIZE);
    qrscanner.setBuffer(qrbuf, SPECTER_HOST_INPUT_SIZE-1);
    tmax = timeout;
}

void host_request_data(){
    host_flush();
    wait(0.3);
    host_flags |= HOST_LISTEN_ONCE;
    qrscanner.trigger = 0;
    t.reset();
    t.start();
}

int host_data_available(){
    if(qrscanner.getStatus() == QR_EXTERNAL){
        return strlen(qrbuf);
    }
    return 0;
}

// this communication channel doesn't support sending data
int host_send(uint8_t * data, size_t len){
    return 0;
}

void host_flush(){
    qrscanner.trigger = 1;
    host_flags = host_flags & 0xE;
    memset(qrbuf, 0, SPECTER_HOST_INPUT_SIZE);
    qrscanner.setBuffer(qrbuf, SPECTER_HOST_INPUT_SIZE);
}

size_t host_read(uint8_t * buf, size_t len){
    size_t cur = strlen(qrbuf);
    if(len > cur){
        len = cur;
    }
    memcpy(buf, qrbuf, len);
    cur -= len;
    memcpy(qrbuf, qrbuf+len, cur);
    memset(qrbuf+cur, 0, len);
    return len;
}

uint8_t * host_get_data(){
    return (uint8_t *)qrbuf;
}
