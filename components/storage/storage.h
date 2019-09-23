#ifndef STORAGE_H
#define STORAGE_H

#define STORAGE_OK 0

int storage_init();
int storage_erase();

// reckless storage
int storage_save_mnemonic(const char * mnemonic);
int storage_load_mnemonic(char ** mnemonic);
int storage_delete_mnemonic();

// void listRoot();
// int save(const char * fname, const char * content);
// bool dirExists(const char * dirname);
// int makeDir(const char * dirname);
// int erase();

#endif