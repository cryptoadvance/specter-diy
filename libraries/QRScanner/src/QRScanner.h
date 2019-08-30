/** @file readline.h
 * QRScanner class working with QR Scanner module
 * for example MIKROE Barcode Click https://www.mikroe.com/barcode-click
 * or Waveshare Barcode Scanner https://www.waveshare.com/barcode-scanner-module.htm
 *
 * Example:
 * @code
 *   #include <mbed.h>
 *   #include <QRScanner.h>
 *
 *   Serial pc(SERIAL_TX, SERIAL_RX, 115200);
 *   QRScanner qrscanner(D5, D1, D0);
 *
 *   int main() {
 *
 *       pc.printf("Ready to scan QR code\n");
 *
 *       while(1){
 *       char c = pc.getc();
 *       if(c=='s'){
 *           char buffer[1000] = "";
 *           int qr_status = qrscanner.scan(buffer, sizeof(buffer)); // By default 3s timeout
 *
 *           if(qr_status == QR_OK){
 *               pc.printf("Success! %s\n", buffer);
 *           }
 *           if(qr_status == QR_OVERFLOW){
 *               pc.printf("Fail! Overflow! %s\n", buffer);
 *           }
 *           if(qr_status == QR_TIMEOUT){
 *               pc.printf("Fail! Timeout! %s\n", buffer);
 *           }
 *       }
 *   }
 * @endcode
 */
#ifndef __QRSCANNER_H__
#define __QRSCANNER_H__

#include <mbed.h>

#define QR_EXTERNAL 2 // when qr scanner was triggered by the button
#define QR_OK 1
#define QR_SCANNING 0
#define QR_OVERFLOW -1
#define QR_TIMEOUT -2

class QRScanner{
private:
    void rx_interrupt();
    char * rx_buffer;
    size_t buf_len = 0;
    volatile size_t rx_cur = 0;
    volatile int qr_status = 0;
    RawSerial serial;
public:
    DigitalOut trigger;
    // constructor. Trigger pin to start scanning, Tx pin, Rx pin and baudrate for serial port.
    QRScanner(PinName triggerPin, PinName txPin, PinName rxPin, int baudrate=9600);
    // tries to scan QR code and puts the result into buffer.
    int scan(char * buffer, size_t len, float timeout=3);
    // defines the buffer to use for qr scanning.
    void setBuffer(char * buffer, size_t len);
    int getStatus() const;
};

#endif // __QRSCANNER_H__
