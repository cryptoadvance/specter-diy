#include "storage.h"
#include "mbed.h"
#include "QSPIFBlockDevice.h"
#include "BlockDevice.h"
#include "LittleFileSystem.h"

QSPIFBlockDevice bd(MBED_CONF_QSPIF_QSPI_IO0,MBED_CONF_QSPIF_QSPI_IO1,MBED_CONF_QSPIF_QSPI_IO2,MBED_CONF_QSPIF_QSPI_IO3,
        MBED_CONF_QSPIF_QSPI_SCK,MBED_CONF_QSPIF_QSPI_CSN,MBED_CONF_QSPIF_QSPI_POLARITY_MODE,MBED_CONF_QSPIF_QSPI_FREQ);
LittleFileSystem fs("internal", &bd);

int storage_erase(){
    // FIXME: should erase everything
    // FIXME: should also zero the whole memory
    int err = fs.reformat(NULL);
    return err;
    // return fs.remove("/internal/gui/calibration");
}

void listRoot(){
    // Display the root directory
    printf("Opening the root directory... ");
    DIR *d = opendir("/internal/");
    printf("%s\r\n", (!d ? "Fail :(" : "OK"));
    if (!d) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    printf("root directory:\r\n");
    while (true) {
        struct dirent *e = readdir(d);
        if (!e) {
            break;
        }

        printf("    %s\r\n", e->d_name);
    }

    printf("Closing the root directory... ");
    int err = closedir(d);
    printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
    if (err < 0) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }
}

int storage_init(){
    int err = fs.mount(&bd);
    printf("%s\r\n", (err ? "Fail :(" : "OK"));
    if (err) {
        printf("No filesystem found, formatting...\r\n");
        err = fs.reformat(&bd);
        printf("%s\r\n", (err ? "Fail :(" : "OK"));
        if (err) {
            printf("error: %s (%d)\r\n", strerror(-err), err);
            return err;
        }
    }
    return STORAGE_OK;
}

int save(const char * fname, const char * content){
    printf("Opening \"%s\"... ", fname);
    char * fullname = (char *)calloc(strlen(fname)+5, sizeof(char));
    sprintf(fullname, "/internal/%s", fname);
    FILE *f = fopen(fullname, "w+");
    free(fullname);
    printf("%s\r\n", (!f ? "Fail :(" : "OK"));
    if(!f){
        error("error: %s (%d)\r\n", strerror(errno), -errno);
        return errno;
    }

    int res = fprintf(f, "%s", content);
    if (res < 0) {
        printf("Fail :(\r\n");
        error("error: %s (%d)\r\n", strerror(errno), -errno);
        return errno;
    }
    return res;
}

bool dirExists(const char * dirname){
    char * fullname = (char *)calloc(strlen(dirname)+5, sizeof(char));
    sprintf(fullname, "/internal/%s", dirname);
    DIR *d = opendir(fullname);
    free(fullname);
    return !!d;
}

int makeDir(const char * dirname){
    char * fullname = (char *)calloc(strlen(dirname)+5, sizeof(char));
    sprintf(fullname, "/internal/%s", dirname);
    int err = mkdir(fullname, 0777);
    free(fullname);
    return err;
}
#if 0
static int qspi_init(){
    int err = fs.mount(&bd);
    printf("%s\r\n", (err ? "Fail :(" : "OK"));
    if (err) {
        // Reformat if we can't mount the filesystem
        // this should only happen on the first boot
        printf("No filesystem found, formatting...\r\n");
        err = fs.reformat(&bd);
        printf("%s\r\n", (err ? "Fail :(" : "OK"));
        if (err) {
            error("error: %s (%d)\r\n", strerror(-err), err);
        }
    }
    printf("Opening \"/internal/numbers.txt\"... ");
    FILE *f = fopen("/internal/numbers.txt", "r+");
    printf("%s\r\n", (!f ? "Fail :(" : "OK"));
    if (!f) {
        // Create the numbers file if it doesn't exist
        printf("No file found, creating a new file... ");
        f = fopen("/internal/numbers.txt", "w+");
        printf("%s\r\n", (!f ? "Fail :(" : "OK"));
        if (!f) {
            error("error: %s (%d)\r\n", strerror(errno), -errno);
        }

        for (int i = 0; i < 10; i++) {
            printf("\rWriting numbers (%d/%d)... ", i, 10);
            err = fprintf(f, "    %d\r\n", i);
            if (err < 0) {
                printf("Fail :(\r\n");
                error("error: %s (%d)\r\n", strerror(errno), -errno);
            }
        }
        printf("\rWriting numbers (%d/%d)... OK\r\n", 10, 10);

        printf("Seeking file... ");
        err = fseek(f, 0, SEEK_SET);
        printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
        if (err < 0) {
            error("error: %s (%d)\r\n", strerror(errno), -errno);
        }
    }

    // Go through and increment the numbers
    for (int i = 0; i < 10; i++) {
        printf("\rIncrementing numbers (%d/%d)... ", i, 10);

        // Get current stream position
        long pos = ftell(f);

        // Parse out the number and increment
        int32_t number;
        fscanf(f, "%d", &number);
        number += 1;

        // Seek to beginning of number
        fseek(f, pos, SEEK_SET);

        // Store number
        fprintf(f, "    %d\r\n", number);

        // Flush between write and read on same file
        fflush(f);
    }
    printf("\rIncrementing numbers (%d/%d)... OK\r\n", 10, 10);

    // Close the file which also flushes any cached writes
    printf("Closing \"/internal/numbers.txt\"... ");
    err = fclose(f);
    printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
    if (err < 0) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    // Display the root directory
    printf("Opening the root directory... ");
    DIR *d = opendir("/internal/");
    printf("%s\r\n", (!d ? "Fail :(" : "OK"));
    if (!d) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    printf("root directory:\r\n");
    while (true) {
        struct dirent *e = readdir(d);
        if (!e) {
            break;
        }

        printf("    %s\r\n", e->d_name);
    }

    printf("Closing the root directory... ");
    err = closedir(d);
    printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
    if (err < 0) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    // Display the numbers file
    printf("Opening \"/internal/numbers.txt\"... ");
    f = fopen("/internal/numbers.txt", "r");
    printf("%s\r\n", (!f ? "Fail :(" : "OK"));
    if (!f) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    printf("numbers:\r\n");
    while (!feof(f)) {
        int c = fgetc(f);
        printf("%c", c);
    }

    printf("\rClosing \"/internal/numbers.txt\"... ");
    err = fclose(f);
    printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
    if (err < 0) {
        error("error: %s (%d)\r\n", strerror(errno), -errno);
    }

    // Tidy up
    printf("Unmounting... ");
    err = fs.unmount();
    printf("%s\r\n", (err < 0 ? "Fail :(" : "OK"));
    if (err < 0) {
        error("error: %s (%d)\r\n", strerror(-err), err);
    }

    printf("Mbed OS filesystem example done!\r\n");
}
#endif