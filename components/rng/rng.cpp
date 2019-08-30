#include "rng.h"

static RNG_HandleTypeDef rng;

int rng_init(){
  __HAL_RCC_RNG_CLK_ENABLE();
  rng.Instance = RNG;
  if(HAL_RNG_Init(&rng) != HAL_OK){
    return 0;
  }
  return 1;
}

uint32_t rng_get_random_number(void){
  uint32_t rnd = 0xff;
  if(HAL_RNG_GenerateRandomNumber(&rng, &rnd) != HAL_OK){
    return 0;
  }
  return rnd;
}

size_t rng_get_random_buffer(uint8_t * arr, size_t len){
    for(uint i=0; 4*i<len; i++){
        uint32_t r = rng_get_random_number();
        if( i*4+1< len ){
            memcpy(arr+i*4, &r, 4);
        }else{
            memcpy(arr+i*4, &r, len-i*4);
        }
    }
    return len;
}
