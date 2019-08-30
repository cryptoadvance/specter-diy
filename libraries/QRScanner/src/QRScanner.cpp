#include "QRScanner.h"

QRScanner::QRScanner(PinName triggerPin, PinName txPin, PinName rxPin, int baudrate):
                                                         serial(txPin, rxPin, baudrate), trigger(triggerPin){
    trigger = 1;
    serial.attach(this, &QRScanner::rx_interrupt, RawSerial::RxIrq);
};

int QRScanner::scan(char * buffer, size_t len, float timeout){
    rx_buffer = buffer;
    buf_len = len;
    qr_status = QR_SCANNING;
    rx_cur = 0;
    memset(rx_buffer, 0, sizeof(rx_buffer));
    Timer t;
    t.start();
    trigger = 0;
    float dt = 0;
    while(qr_status == 0 && dt < timeout){
        dt = t.read();
    }
    t.stop();
    trigger = 1;
    if(dt >= timeout){
        qr_status = QR_TIMEOUT;
    }
    rx_buffer = NULL;
    buf_len = 0;
    return qr_status;
}
void QRScanner::setBuffer(char * buffer, size_t len){
    rx_buffer = buffer;
    buf_len = len;
    qr_status = QR_OK;
    rx_cur = 0;
    memset(rx_buffer, 0, sizeof(rx_buffer));
}
int QRScanner::getStatus() const{
    int status = qr_status;
    return status;
}
void QRScanner::rx_interrupt(){
    while(serial.readable() && rx_cur < buf_len-1){
        if(rx_buffer != NULL){
            rx_buffer[rx_cur] = serial.getc();
            rx_cur ++;
        }
    }
    rx_buffer[rx_cur] = 0; // eol
    if(rx_buffer[rx_cur-1] == 0x0d){
        rx_cur --;
        rx_buffer[rx_cur] = 0;
        if(qr_status == QR_SCANNING){
            qr_status = QR_OK;
        }else{
            qr_status = QR_EXTERNAL;
            rx_buffer = NULL;
            buf_len = 0;
        }
    }
    if(rx_cur >= buf_len-1){
        qr_status = QR_OVERFLOW;
    }
}
