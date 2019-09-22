#ifndef __GUI_H__
#define __GUI_H__

#include <stdint.h>

/** possible GUI actions (main needs to handle them) */
#define GUI_NO_ACTION            0
#define GUI_BACK                 1
#define GUI_GENERATE_KEY         2
#define GUI_SECURE_SHUTDOWN      3
#define GUI_PROCESS_MNEMONIC     4
#define GUI_PROCESS_PASSWORD     5
#define GUI_PROCESS_NETWORK      6
#define GUI_SHOW_XPUB            7
#define GUI_VERIFY_ADDRESS       8
#define GUI_SIGN_PSBT            9
#define GUI_PSBT_CONFIRMED      10

/** structure to display output */
typedef struct _txout_t {
    char * address;
    uint64_t amount;
    uint8_t is_change;
    char * warning;
} txout_t;

void gui_init();
void gui_start();
void gui_update();
int gui_get_action();
void gui_clear_action();
int gui_get_value();
char * gui_get_str(); // not const because we will wipe it from main

void gui_set_available_networks(const char * names[]);
void gui_set_network(uint8_t index);
void gui_set_default_xpubs(const char * single, const char * multisig);

void gui_show_init_screen();
void gui_show_mnemonic(const char * mnemonic);
void gui_get_password();
void gui_show_main_screen();
void gui_show_xpub(const char * fingerprint, const char * derivation, const char * xpub);
void gui_show_addresses(const char * derivation, const char * segwit_addr, const char * base58_addr);
void gui_show_psbt(uint64_t out_amount, uint64_t change_amount, uint64_t fee, uint8_t num_outputs, txout_t * outputs);

void gui_calibrate();

#endif