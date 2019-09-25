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

int storage_save_mnemonic(const char * mnemonic){
    FILE *f = fopen("/internal/mnemonic", "w");
    if(!f){
        return -1;
    }
    fprintf(f, mnemonic);
    fclose(f);
    return 0;
}

int storage_load_mnemonic(char ** mnemonic){
    FILE *f = fopen("/internal/mnemonic", "r");
    if(!f){
        return -1;
    }
    // TODO: check length
    char content[300];
    fscanf(f,"%[^\n]", content);
    *mnemonic = (char *)malloc(strlen(content)+1);
    strcpy(*mnemonic, content);
    memset(content, 0, sizeof(content));
    fclose(f);
    return 0;
}

int storage_delete_mnemonic(){
    return remove("/internal/mnemonic");
}

int storage_maybe_mkdir(const char * path){
    DIR *d = opendir(path);
    if(!d){ // doesnt exist
        int err = mkdir(path, 0777);
        return err;
    }
    return 0;
}

int storage_get_file_count(const char * path, const char * extension){
    DIR *d = opendir(path);
    if(!d){
        return -1;
    }
    int count = 0;
    while(1){
        struct dirent *e = readdir(d);
        if(!e){
            break;
        }
        if(strlen(e->d_name) >= strlen(extension)){
            if(strcmp(e->d_name + strlen(e->d_name) - strlen(extension), extension) == 0){
                count++;
            }
        }
    }
    closedir(d);
    return count;
}

static int get_available_file_id(const char * path, const char * extension){
    DIR *d = opendir(path);
    if(!d){
        return -1;
    }
    int num = 0;
    while(1){
        struct dirent *e = readdir(d);
        if(!e){
            break;
        }
        if(strlen(e->d_name) >= strlen(extension)){
            if(strcmp(e->d_name - strlen(extension), extension) == 0){
                char ext[20];
                int n;
                sscanf(e->d_name, "%d.", &n);
                if(num < n+1){
                    num = n+1;
                }
            }
        }
    }
    closedir(d);
    return num;
}

int storage_push(const char * path, const char * buf, const char * extension){
    int num = get_available_file_id(path, extension);
    if(num < 0){
        return num;
    }
    char fname[100];
    sprintf(fname, "%s/%d%s", path, num, extension);
    printf("saved as %s\r\n", fname);
    FILE *f = fopen(fname, "w");
    fprintf(f, buf);
    fclose(f);
    return num;
}

int storage_read(const char * path, int num, const char * extension, char ** buf){
    char fname[100];
    sprintf(fname, "%s/%d%s", path, num, extension);
    FILE *f = fopen(fname, "r");
    if(!f){
        return -1;
    }
    fseek(f, 0, SEEK_END);
    int sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    *buf = (char *)calloc(sz+1, 1);
    fread(*buf, 1, sz, f);
    fclose(f);
    return sz+1;
}


#if 0
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