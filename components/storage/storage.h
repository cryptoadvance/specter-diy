#ifndef STORAGE_H
#define STORAGE_H

#define STORAGE_OK 0

int storage_init();
int storage_erase();

// reckless storage
int storage_save_mnemonic(const char * mnemonic);
int storage_load_mnemonic(char ** mnemonic);
int storage_delete_mnemonic();

#ifdef __cplusplus
extern "C" {
#endif

int storage_maybe_mkdir(const char * path);
int storage_get_file_count(const char * path, const char * extension);
int storage_push(const char * path, const char * buf, const char * extension);
int storage_del(const char * path, int num, const char * extension);

#ifdef __cplusplus
}
#endif

// void listRoot();
// int save(const char * fname, const char * content);
// bool dirExists(const char * dirname);
// int makeDir(const char * dirname);
// int erase();

#endif