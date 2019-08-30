/**
 * @file disp.c
 *
 */

/*********************
 *      INCLUDES
 *********************/
#include "tft.h"
#include "lv_conf.h"
#include <string.h>

#include "stm32f4xx.h"
#include "stm32469i_discovery.h"
#include "stm32469i_discovery_lcd.h"
#include "stm32469i_discovery_sdram.h"
/*********************
 *      DEFINES
 *********************/

#if TFT_EXT_FB != 0

#define SDRAM_BANK_ADDR			SDRAM_DEVICE_ADDR 		/* Set in stm32469i_discovery_sdram.h (0xC0000000) */
#define SDRAM_TIMEOUT     ((uint32_t)0xFFFF)

#endif

/* DMA Stream parameters definitions. You can modify these parameters to select
   a different DMA Stream and/or channel.
   But note that only DMA2 Streams are capable of Memory to Memory transfers. */
#define DMA_STREAM               DMA2_Stream0
#define DMA_CHANNEL              DMA_CHANNEL_0
#define DMA_STREAM_IRQ           DMA2_Stream0_IRQn
#define DMA_STREAM_IRQHANDLER    DMA2_Stream0_IRQHandler

/**********************
 *      TYPEDEFS
 **********************/
static DSI_VidCfgTypeDef hdsivideo_handle;

/**********************
 *  STATIC PROTOTYPES
 **********************/

/*These 3 functions are needed by LittlevGL*/
static void tft_flush(lv_disp_drv_t * drv, const lv_area_t * area, lv_color_t * color_p);
#if TFT_USE_GPU != 0
static void gpu_mem_blend(lv_disp_drv_t * drv, lv_color_t * dest, const lv_color_t * src, uint32_t length, lv_opa_t opa);
static void gpu_mem_fill(lv_disp_drv_t * disp_drv, lv_color_t * dest_buf, lv_coord_t dest_width,
        const lv_area_t * fill_area, lv_color_t color);
#endif

/*LCD*/
static void LCD_Config(void);
void HAL_LTDC_MspDeInit(LTDC_HandleTypeDef *hltdc);
void HAL_LTDC_MspInit(LTDC_HandleTypeDef *hltdc);
#if TFT_USE_GPU != 0
static void DMA2D_Config(void);
#endif

/*SD RAM*/
#if TFT_EXT_FB != 0
static void SDRAM_Init(void);
static void SDRAM_Initialization_Sequence(SDRAM_HandleTypeDef *hsdram, FMC_SDRAM_CommandTypeDef *Command);
#endif

/*DMA to flush to frame buffer*/
static void DMA_Config(void);
static void DMA_TransferComplete(DMA_HandleTypeDef *han);
static void DMA_TransferError(DMA_HandleTypeDef *han);

static void Error_Handler(void);
/**********************
 *  STATIC VARIABLES
 **********************/


// DSI_HandleTypeDef hdsi_eval;
// LTDC_HandleTypeDef hltdc_eval;

#if TFT_USE_GPU != 0
static DMA2D_HandleTypeDef     Dma2dHandle;
#endif

#if TFT_EXT_FB != 0
SDRAM_HandleTypeDef hsdram;
FMC_SDRAM_TimingTypeDef SDRAM_Timing;
FMC_SDRAM_CommandTypeDef command;
static __IO uint16_t * my_fb = (__IO uint16_t*) (SDRAM_BANK_ADDR);
#else
static uint16_t my_fb[TFT_HOR_RES * TFT_VER_RES];
#endif


DMA_HandleTypeDef     DmaHandle;
static lv_disp_drv_t disp_drv;
static int32_t x1_flush;
static int32_t y1_flush;
static int32_t x2_flush;
static int32_t y2_fill;
static int32_t y_fill_act;
static const lv_color_t * buf_to_flush;

/**********************
 *      MACROS
 **********************/

/**********************
 *   GLOBAL FUNCTIONS
 **********************/

/**
 * Initialize your display here
 */
void tft_init(void)
{
  static lv_color_t disp_buf1[LV_VER_RES_MAX * 30];
  static lv_disp_buf_t buf;
  lv_disp_buf_init(&buf, disp_buf1, NULL, LV_HOR_RES_MAX * 30);

  lv_disp_drv_init(&disp_drv);

#if TFT_EXT_FB != 0
  SDRAM_Init();
#endif
  LCD_Config();
  DMA_Config();

  disp_drv.buffer = &buf;
  disp_drv.flush_cb = tft_flush;
#if TFT_USE_GPU != 0
  DMA2D_Config();
  disp_drv.gpu_blend_cb = gpu_mem_blend;
  disp_drv.gpu_fill_cb = gpu_mem_fill;
#endif
  lv_disp_drv_register(&disp_drv);
}

/**
 * Put a color map to a rectangular area
 * @param x1 left coordinate of the rectangle
 * @param x2 right coordinate of the rectangle
 * @param y1 top coordinate of the rectangle
 * @param y2 bottom coordinate of the rectangle
 * @param color_p pointer to an array of colors
 */
static void tft_flush(lv_disp_drv_t * drv, const lv_area_t * area, lv_color_t * color_p)
{
  /*Return if the area is out the screen*/
  if(area->x2 < 0) return;
  if(area->y2 < 0) return;
  if(area->x1 > TFT_HOR_RES - 1) return;
  if(area->y1 > TFT_VER_RES - 1) return;

  /*Truncate the area to the screen*/
  int32_t act_x1 = area->x1 < 0 ? 0 : area->x1;
  int32_t act_y1 = area->y1 < 0 ? 0 : area->y1;
  int32_t act_x2 = area->x2 > TFT_HOR_RES - 1 ? TFT_HOR_RES - 1 : area->x2;
  int32_t act_y2 = area->y2 > TFT_VER_RES - 1 ? TFT_VER_RES - 1 : area->y2;

  x1_flush = act_x1;
  y1_flush = act_y1;
  x2_flush = act_x2;
  y2_fill = act_y2;
  y_fill_act = act_y1;
  buf_to_flush = color_p;


    /*##-7- Start the DMA transfer using the interrupt mode #*/
    /* Configure the source, destination and buffer size DMA fields and Start DMA Stream transfer */
    /* Enable All the DMA interrupts */
  HAL_StatusTypeDef err;
  err = HAL_DMA_Start_IT(&DmaHandle,(uint32_t)buf_to_flush, (uint32_t)&my_fb[y_fill_act * TFT_HOR_RES + x1_flush],
        (x2_flush - x1_flush + 1));
  if(err != HAL_OK)
  {
    while(1); /*Halt on error*/
  }
}

#if TFT_USE_GPU != 0

/**
 * Copy pixels to destination memory using opacity
 * @param dest a memory address. Copy 'src' here.
 * @param src pointer to pixel map. Copy it to 'dest'.
 * @param length number of pixels in 'src'
 * @param opa opacity (0, OPA_TRANSP: transparent ... 255, OPA_COVER, fully cover)
 */
static void gpu_mem_blend(lv_disp_drv_t * drv, lv_color_t * dest, const lv_color_t * src, uint32_t length, lv_opa_t opa)
{
  /*Wait for the previous operation*/
  HAL_DMA2D_PollForTransfer(&Dma2dHandle, 100);
  Dma2dHandle.Init.Mode         = DMA2D_M2M_BLEND;
  /* DMA2D Initialization */
  if(HAL_DMA2D_Init(&Dma2dHandle) != HAL_OK)
  {
    /* Initialization Error */
    while(1);
  }

  Dma2dHandle.LayerCfg[1].InputAlpha = opa;
    HAL_DMA2D_ConfigLayer(&Dma2dHandle, 1);
  HAL_DMA2D_BlendingStart(&Dma2dHandle, (uint32_t) src, (uint32_t) dest, (uint32_t)dest, length, 1);
}

static void gpu_mem_fill(lv_disp_drv_t * disp_drv, lv_color_t * dest_buf, lv_coord_t dest_width,
        const lv_area_t * fill_area, lv_color_t color)
{
  /*Wait for the previous operation*/
  HAL_DMA2D_PollForTransfer(&Dma2dHandle, 100);

   Dma2dHandle.Init.Mode         = DMA2D_R2M;
   /* DMA2D Initialization */
   if(HAL_DMA2D_Init(&Dma2dHandle) != HAL_OK)
   {
     /* Initialization Error */
     while(1);
   }

   Dma2dHandle.LayerCfg[1].InputAlpha = 0xff;
   HAL_DMA2D_ConfigLayer(&Dma2dHandle, 1);

   lv_color_t * dest_buf_ofs = dest_buf;

   dest_buf_ofs += dest_width * fill_area->y1;
   dest_buf_ofs += fill_area->x1;
   lv_coord_t area_w = lv_area_get_width(fill_area);

   uint32_t i;
   for(i = fill_area->y1; i <= fill_area->y2; i++) {
     /*Wait for the previous operation*/
     HAL_DMA2D_PollForTransfer(&Dma2dHandle, 100);
     HAL_DMA2D_BlendingStart(&Dma2dHandle, (uint32_t) lv_color_to32(color), (uint32_t) dest_buf_ofs, (uint32_t)dest_buf_ofs, area_w, 1);
     dest_buf_ofs += dest_width;
   }
}

#endif

static void LCD_Config(void)
{
	LTDC_LayerCfgTypeDef pLayerCfg;
	BSP_LCD_InitEx(LCD_ORIENTATION_PORTRAIT);
	BSP_LCD_LayerDefaultInit(0, (uint32_t)my_fb);
}

#if TFT_USE_GPU != 0
/**
  * @brief  DMA2D Transfer completed callback
  * @param  hdma2d: DMA2D handle.
  * @note   This example shows a simple way to report end of DMA2D transfer, and
  *         you can add your own implementation.
  * @retval None
  */
static void DMA2D_TransferComplete(DMA2D_HandleTypeDef *hdma2d)
{

}

/**
  * @brief  DMA2D error callbacks
  * @param  hdma2d: DMA2D handle
  * @note   This example shows a simple way to report DMA2D transfer error, and you can
  *         add your own implementation.
  * @retval None
  */
static void DMA2D_TransferError(DMA2D_HandleTypeDef *hdma2d)
{

}

/**
  * @brief DMA2D configuration.
  * @note  This function Configure the DMA2D peripheral :
  *        1) Configure the Transfer mode as memory to memory with blending.
  *        2) Configure the output color mode as RGB565 pixel format.
  *        3) Configure the foreground
  *          - first image loaded from FLASH memory
  *          - constant alpha value (decreased to see the background)
  *          - color mode as RGB565 pixel format
  *        4) Configure the background
  *          - second image loaded from FLASH memory
  *          - color mode as RGB565 pixel format
  * @retval None
  */
static void DMA2D_Config(void)
{
  /* Configure the DMA2D Mode, Color Mode and output offset */
  Dma2dHandle.Init.Mode         = DMA2D_M2M_BLEND;
  Dma2dHandle.Init.ColorMode    = DMA2D_RGB565 ;
  Dma2dHandle.Init.OutputOffset = 0x0;

  /* DMA2D Callbacks Configuration */
  Dma2dHandle.XferCpltCallback  = DMA2D_TransferComplete;
  Dma2dHandle.XferErrorCallback = DMA2D_TransferError;

  /* Foreground Configuration */
  Dma2dHandle.LayerCfg[1].AlphaMode = DMA2D_REPLACE_ALPHA;
  Dma2dHandle.LayerCfg[1].InputAlpha = 0xFF;
  Dma2dHandle.LayerCfg[1].InputColorMode = DMA2D_INPUT_RGB565;
  Dma2dHandle.LayerCfg[1].InputOffset = 0x0;

  /* Background Configuration */
  Dma2dHandle.LayerCfg[0].AlphaMode = DMA2D_REPLACE_ALPHA;
  Dma2dHandle.LayerCfg[0].InputAlpha = 0xFF;
  Dma2dHandle.LayerCfg[0].InputColorMode = DMA2D_INPUT_RGB565;
  Dma2dHandle.LayerCfg[0].InputOffset = 0x0;

  Dma2dHandle.Instance   = DMA2D;

  /* DMA2D Initialization */
  if(HAL_DMA2D_Init(&Dma2dHandle) != HAL_OK)
  {
    /* Initialization Error */
    Error_Handler();
  }

  HAL_DMA2D_ConfigLayer(&Dma2dHandle, 0);
  HAL_DMA2D_ConfigLayer(&Dma2dHandle, 1);
}
#endif


/**
  * @brief  This function handles LTDC global interrupt request.
  * @param  None
  * @retval None
  */
// void LTDC_IRQHandler(void)
// {
//   // HAL_LTDC_IRQHandler(&hltdc_eval);
// }

/**
  * @brief LTDC MSP Initialization
  *        This function configures the hardware resources used in this example:
  *           - Peripheral's clock enable
  *           - Peripheral's GPIO Configuration
  * @param hltdc: LTDC handle pointer
  * @retval None
  */
void HAL_LTDC_MspInit(LTDC_HandleTypeDef *hltdc)
{
  GPIO_InitTypeDef GPIO_Init_Structure;

  /*##-1- Enable peripherals and GPIO Clocks #################################*/
  /* Enable the LTDC Clock */
  __HAL_RCC_LTDC_CLK_ENABLE();

#if 0
  /* Enable GPIOs clock */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();

  /*##-2- Configure peripheral GPIO ##########################################*/

  /* LTDC pins configuraiton: PA3 -- 12 */
  GPIO_Init_Structure.Pin = GPIO_PIN_3 | GPIO_PIN_4 | GPIO_PIN_6 |
                                GPIO_PIN_11 | GPIO_PIN_12;
  GPIO_Init_Structure.Mode = GPIO_MODE_AF_PP;
  GPIO_Init_Structure.Pull = GPIO_NOPULL;
  GPIO_Init_Structure.Speed = GPIO_SPEED_FAST;
  GPIO_Init_Structure.Alternate= GPIO_AF14_LTDC;
  HAL_GPIO_Init(GPIOA, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PB8 -- 11 */
  GPIO_Init_Structure.Pin = GPIO_PIN_8 | \
                             GPIO_PIN_9 ;//| GPIO_PIN_10 | GPIO_PIN_11;
  HAL_GPIO_Init(GPIOB, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PC6 -- 10 */
  GPIO_Init_Structure.Pin = GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOC, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PD3 -- 6 */
  GPIO_Init_Structure.Pin = GPIO_PIN_3 | GPIO_PIN_6;
  HAL_GPIO_Init(GPIOD, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PF10 */
  GPIO_Init_Structure.Pin = GPIO_PIN_10;
  HAL_GPIO_Init(GPIOF, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PG6 -- 11 */
  GPIO_Init_Structure.Pin =  GPIO_PIN_7 | \
                             GPIO_PIN_11;
  HAL_GPIO_Init(GPIOG, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PB0 -- 1 */
  GPIO_Init_Structure.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  GPIO_Init_Structure.Alternate = GPIO_AF9_LTDC;
  HAL_GPIO_Init(GPIOB, &GPIO_Init_Structure);

  /* LTDC pins configuraiton: PG10 -- 12 */
  GPIO_Init_Structure.Pin = GPIO_PIN_10 | GPIO_PIN_12;
  HAL_GPIO_Init(GPIOG, &GPIO_Init_Structure);
#endif
  /* Set LTDC Interrupt to the lowest priority */
  HAL_NVIC_SetPriority(LTDC_IRQn, 0x5, 0);

  /* Enable LTDC Interrupt */
  HAL_NVIC_EnableIRQ(LTDC_IRQn);
}

/**
  * @brief LTDC MSP De-Initialization
  *        This function frees the hardware resources used in this example:
  *          - Disable the Peripheral's clock
  * @param hltdc: LTDC handle pointer
  * @retval None
  */
void HAL_LTDC_MspDeInit(LTDC_HandleTypeDef *hltdc)
{

  /*##-1- Reset peripherals ##################################################*/
  /* Enable LTDC reset state */
  __HAL_RCC_LTDC_FORCE_RESET();

  /* Release LTDC from reset state */
  __HAL_RCC_LTDC_RELEASE_RESET();
}
/**
  * @brief DMA2D MSP Initialization
  *        This function configures the hardware resources used in this example:
  *           - Peripheral's clock enable
  *           - Peripheral's GPIO Configuration
  * @param hdma2d: DMA2D handle pointer
  * @retval None
  */
void HAL_DMA2D_MspInit(DMA2D_HandleTypeDef *hdma2d)
{
  /*##-1- Enable peripherals and GPIO Clocks #################################*/
  __HAL_RCC_DMA2D_CLK_ENABLE();

  /*##-2- NVIC configuration  ################################################*/
  /* NVIC configuration for DMA2D transfer complete interrupt */
  HAL_NVIC_SetPriority(DMA2D_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA2D_IRQn);
}


#if TFT_EXT_FB != 0

static void SDRAM_Init(void)
{
  /* SDRAM device configuration */
  hsdram.Instance = FMC_SDRAM_DEVICE;

  /* Timing configuration for 90 MHz of SDRAM clock frequency (180MHz/2) */
  /* TMRD: 2 Clock cycles */
  SDRAM_Timing.LoadToActiveDelay    = 2;
  /* TXSR: min=70ns (6x11.90ns) */
  SDRAM_Timing.ExitSelfRefreshDelay = 7;
  /* TRAS: min=42ns (4x11.90ns) max=120k (ns) */
  SDRAM_Timing.SelfRefreshTime      = 4;
  /* TRC:  min=63 (6x11.90ns) */
  SDRAM_Timing.RowCycleDelay        = 7;
  /* TWR:  2 Clock cycles */
  SDRAM_Timing.WriteRecoveryTime    = 2;
  /* TRP:  15ns => 2x11.90ns */
  SDRAM_Timing.RPDelay              = 2;
  /* TRCD: 15ns => 2x11.90ns */
  SDRAM_Timing.RCDDelay             = 2;

  hsdram.Init.SDBank             = FMC_SDRAM_BANK1;
  hsdram.Init.ColumnBitsNumber   = FMC_SDRAM_COLUMN_BITS_NUM_8;
  hsdram.Init.RowBitsNumber      = FMC_SDRAM_ROW_BITS_NUM_12;
  hsdram.Init.MemoryDataWidth    = SDRAM_MEMORY_WIDTH;
  hsdram.Init.InternalBankNumber = FMC_SDRAM_INTERN_BANKS_NUM_4;
  hsdram.Init.CASLatency         = FMC_SDRAM_CAS_LATENCY_3;
  hsdram.Init.WriteProtection    = FMC_SDRAM_WRITE_PROTECTION_DISABLE;
  hsdram.Init.SDClockPeriod      = SDCLOCK_PERIOD;
  hsdram.Init.ReadBurst          = FMC_SDRAM_RBURST_DISABLE;
  hsdram.Init.ReadPipeDelay      = FMC_SDRAM_RPIPE_DELAY_0;

  /* Initialize the SDRAM controller */
  if(HAL_SDRAM_Init(&hsdram, &SDRAM_Timing) != HAL_OK)
  {
    /* Initialization Error */
    Error_Handler();
  }

  /* Program the SDRAM external device */
  SDRAM_Initialization_Sequence(&hsdram, &command);
}

/**
  * @brief  Perform the SDRAM external memory initialization sequence
  * @param  hsdram: SDRAM handle
  * @param  Command: Pointer to SDRAM command structure
  * @retval None
  */
static void SDRAM_Initialization_Sequence(SDRAM_HandleTypeDef *hsdram, FMC_SDRAM_CommandTypeDef *Command)
{
  __IO uint32_t tmpmrd =0;
  /* Step 3:  Configure a clock configuration enable command */
  Command->CommandMode       = FMC_SDRAM_CMD_CLK_ENABLE;
  Command->CommandTarget     = FMC_SDRAM_CMD_TARGET_BANK1;
  Command->AutoRefreshNumber   = 1;
  Command->ModeRegisterDefinition = 0;

  /* Send the command */
  HAL_SDRAM_SendCommand(hsdram, Command, 0x1000);

  /* Step 4: Insert 100 ms delay */
  HAL_Delay(100);

  /* Step 5: Configure a PALL (precharge all) command */
  Command->CommandMode       = FMC_SDRAM_CMD_PALL;
  Command->CommandTarget       = FMC_SDRAM_CMD_TARGET_BANK1;
  Command->AutoRefreshNumber   = 1;
  Command->ModeRegisterDefinition = 0;

  /* Send the command */
  HAL_SDRAM_SendCommand(hsdram, Command, 0x1000);

  /* Step 6 : Configure a Auto-Refresh command */
  Command->CommandMode       = FMC_SDRAM_CMD_AUTOREFRESH_MODE;
  Command->CommandTarget     = FMC_SDRAM_CMD_TARGET_BANK1;
  Command->AutoRefreshNumber   = 8;
  Command->ModeRegisterDefinition = 0;

  /* Send the command */
  HAL_SDRAM_SendCommand(hsdram, Command, 0x1000);

  /* Step 7: Program the external memory mode register */
  tmpmrd = (uint32_t)SDRAM_MODEREG_BURST_LENGTH_1          |
                     SDRAM_MODEREG_BURST_TYPE_SEQUENTIAL   |
                     SDRAM_MODEREG_CAS_LATENCY_3           |
                     SDRAM_MODEREG_OPERATING_MODE_STANDARD |
                     SDRAM_MODEREG_WRITEBURST_MODE_SINGLE;

  Command->CommandMode = FMC_SDRAM_CMD_LOAD_MODE;
  Command->CommandTarget     = FMC_SDRAM_CMD_TARGET_BANK1;
  Command->AutoRefreshNumber   = 1;
  Command->ModeRegisterDefinition = tmpmrd;

  /* Send the command */
  HAL_SDRAM_SendCommand(hsdram, Command, 0x1000);

  /* Step 8: Set the refresh rate counter */
  /* (15.62 us x Freq) - 20 */
  /* Set the device refresh counter */
  HAL_SDRAM_ProgramRefreshRate(hsdram, REFRESH_COUNT);
}


/**
  * @brief SDRAM MSP Initialization
  *        This function configures the hardware resources used in this example:
  *           - Peripheral's clock enable
  *           - Peripheral's GPIO Configuration
  * @param hsdram: SDRAM handle pointer
  * @retval None
  */
void HAL_SDRAM_MspInit(SDRAM_HandleTypeDef *hsdram)
{
#if 0
  GPIO_InitTypeDef  gpio_init_structure;

  /*##-1- Enable peripherals and GPIO Clocks #################################*/
  /* Enable GPIO clocks */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOI_CLK_ENABLE();
  /* Enable FMC clock */
  __HAL_RCC_FMC_CLK_ENABLE();

  /*##-2- Configure peripheral GPIO ##########################################*/
  /*-- GPIOs Configuration -----------------------------------------------------*/

  /* Common GPIO configuration */
  gpio_init_structure.Mode  = GPIO_MODE_AF_PP;
  gpio_init_structure.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  gpio_init_structure.Pull  = GPIO_PULLUP;
  gpio_init_structure.Alternate = GPIO_AF12_FMC;

  /* GPIOC configuration : PC0 is SDNWE */
  gpio_init_structure.Pin   = GPIO_PIN_0;
  HAL_GPIO_Init(GPIOC, &gpio_init_structure);

  /* GPIOD configuration */
  gpio_init_structure.Pin   = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_8| GPIO_PIN_9 | GPIO_PIN_10 |\
							  GPIO_PIN_14 | GPIO_PIN_15;


  HAL_GPIO_Init(GPIOD, &gpio_init_structure);

  /* GPIOE configuration */
  gpio_init_structure.Pin   = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_7| GPIO_PIN_8 | GPIO_PIN_9 |\
							  GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 |\
							  GPIO_PIN_15;

  HAL_GPIO_Init(GPIOE, &gpio_init_structure);

  /* GPIOF configuration */
  gpio_init_structure.Pin   = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2| GPIO_PIN_3 | GPIO_PIN_4 |\
							  GPIO_PIN_5 | GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 |\
							  GPIO_PIN_15;

  HAL_GPIO_Init(GPIOF, &gpio_init_structure);

  /* GPIOG configuration */
  gpio_init_structure.Pin   = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4| GPIO_PIN_5 | GPIO_PIN_8 |\
							  GPIO_PIN_15;
  HAL_GPIO_Init(GPIOG, &gpio_init_structure);

  /* GPIOH configuration */
  gpio_init_structure.Pin   = GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_8 | GPIO_PIN_9 |\
							  GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 |\
							  GPIO_PIN_15;
  HAL_GPIO_Init(GPIOH, &gpio_init_structure);

  /* GPIOI configuration */
  gpio_init_structure.Pin   = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_4 |\
							  GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_9 | GPIO_PIN_10;
  HAL_GPIO_Init(GPIOI, &gpio_init_structure);
#endif
}

/**
  * @brief SDRAM MSP De-Initialization
  *        This function frees the hardware resources used in this example:
  *          - Disable the Peripheral's clock
  *          - Revert GPIO configuration to their default state
  * @param hsdram: SDRAM handle pointer
  * @retval None
  */
void HAL_SDRAM_MspDeInit(SDRAM_HandleTypeDef *hsdram)
{
#if 0

  HAL_GPIO_DeInit(GPIOC, GPIO_PIN_0);

  HAL_GPIO_DeInit(GPIOD, GPIO_PIN_0 | GPIO_PIN_1  | GPIO_PIN_8 |\
                         GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_14 |\
                         GPIO_PIN_15);

  HAL_GPIO_DeInit(GPIOE, GPIO_PIN_0  | GPIO_PIN_1  | GPIO_PIN_7 |\
                         GPIO_PIN_8  | GPIO_PIN_9  | GPIO_PIN_10 |\
                         GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 |\
                         GPIO_PIN_14 | GPIO_PIN_15);

  HAL_GPIO_DeInit(GPIOF, GPIO_PIN_0  | GPIO_PIN_1 | GPIO_PIN_2 |\
                         GPIO_PIN_3  | GPIO_PIN_4 | GPIO_PIN_5 |\
                         GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 |\
                         GPIO_PIN_14 | GPIO_PIN_15);

  HAL_GPIO_DeInit(GPIOG, GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4 |\
                         GPIO_PIN_5 | GPIO_PIN_8 | GPIO_PIN_15);

  HAL_GPIO_DeInit(GPIOH, GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_8 |\
		  	  	  	  	 GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_11 |\
						 GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 |\
						 GPIO_PIN_15);

  HAL_GPIO_DeInit(GPIOI, GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 |\
		  	  	  	  	 GPIO_PIN_3 | GPIO_PIN_4 | GPIO_PIN_5 |\
						 GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_9 |\
						 GPIO_PIN_10);
#endif
}

#endif


/**
  * @brief  Configure the DMA controller according to the Stream parameters
  *         defined in main.h file
  * @note  This function is used to :
  *        -1- Enable DMA2 clock
  *        -2- Select the DMA functional Parameters
  *        -3- Select the DMA instance to be used for the transfer
  *        -4- Select Callbacks functions called after Transfer complete and
               Transfer error interrupt detection
  *        -5- Initialize the DMA stream
  *        -6- Configure NVIC for DMA transfer complete/error interrupts
  * @param  None
  * @retval None
  */
static void DMA_Config(void)
{
  /*## -1- Enable DMA2 clock #################################################*/
  __HAL_RCC_DMA2_CLK_ENABLE();

  /*##-2- Select the DMA functional Parameters ###############################*/
  DmaHandle.Init.Channel = DMA_CHANNEL;                     /* DMA_CHANNEL_0                    */
  DmaHandle.Init.Direction = DMA_MEMORY_TO_MEMORY;          /* M2M transfer mode                */
  DmaHandle.Init.PeriphInc = DMA_PINC_ENABLE;               /* Peripheral increment mode Enable */
  DmaHandle.Init.MemInc = DMA_MINC_ENABLE;                  /* Memory increment mode Enable     */
  DmaHandle.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD; /* Peripheral data alignment : 16bit */
  DmaHandle.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;    /* memory data alignment : 16bit     */
  DmaHandle.Init.Mode = DMA_NORMAL;                         /* Normal DMA mode                  */
  DmaHandle.Init.Priority = DMA_PRIORITY_HIGH;              /* priority level : high            */
  DmaHandle.Init.FIFOMode = DMA_FIFOMODE_ENABLE;            /* FIFO mode enabled                */
  DmaHandle.Init.FIFOThreshold = DMA_FIFO_THRESHOLD_1QUARTERFULL; /* FIFO threshold: 1/4 full   */
  DmaHandle.Init.MemBurst = DMA_MBURST_SINGLE;              /* Memory burst                     */
  DmaHandle.Init.PeriphBurst = DMA_PBURST_SINGLE;           /* Peripheral burst                 */

  /*##-3- Select the DMA instance to be used for the transfer : DMA2_Stream0 #*/
  DmaHandle.Instance = DMA_STREAM;

  /*##-4- Initialize the DMA stream ##########################################*/
  if(HAL_DMA_Init(&DmaHandle) != HAL_OK)
  {
    /* Turn LED4 on: in case of Initialization Error */
    // BSP_LED_On(LED4);
    while(1)
    {
    }
}

  /*##-5- Select Callbacks functions called after Transfer complete and Transfer error */
  HAL_DMA_RegisterCallback(&DmaHandle, HAL_DMA_XFER_CPLT_CB_ID, DMA_TransferComplete);
  HAL_DMA_RegisterCallback(&DmaHandle, HAL_DMA_XFER_ERROR_CB_ID, DMA_TransferError);

  /*##-6- Configure NVIC for DMA transfer complete/error interrupts ##########*/
  HAL_NVIC_SetPriority(DMA_STREAM_IRQ, 0, 0);
  HAL_NVIC_EnableIRQ(DMA_STREAM_IRQ);
}

/**
  * @brief  DMA conversion complete callback
  * @note   This function is executed when the transfer complete interrupt
  *         is generated
  * @retval None
  */
static void DMA_TransferComplete(DMA_HandleTypeDef *han)
{
  y_fill_act ++;

  if(y_fill_act > y2_fill) {
      lv_disp_flush_ready(&disp_drv);
  } else {
    buf_to_flush += x2_flush - x1_flush + 1;
    /*##-7- Start the DMA transfer using the interrupt mode ####################*/
    /* Configure the source, destination and buffer size DMA fields and Start DMA Stream transfer */
    /* Enable All the DMA interrupts */
    if(HAL_DMA_Start_IT(han,(uint32_t)buf_to_flush, (uint32_t)&my_fb[y_fill_act * TFT_HOR_RES + x1_flush],
              (x2_flush - x1_flush + 1)) != HAL_OK)
    {
      while(1); /*Halt on error*/
    }
  }
}

/**
  * @brief  DMA conversion error callback
  * @note   This function is executed when the transfer error interrupt
  *         is generated during DMA transfer
  * @retval None
  */
static void DMA_TransferError(DMA_HandleTypeDef *han)
{

}



/**
  * @brief  This function handles DMA Stream interrupt request.
  * @param  None
  * @retval None
  */
void DMA_STREAM_IRQHANDLER(void)
{
    /* Check the interrupt and clear flag */
    HAL_DMA_IRQHandler(&DmaHandle);
}


/**
  * @brief  This function is executed in case of error occurrence.
  * @param  None
  * @retval None
  */
static void Error_Handler(void)
{
  while(1)
  {
  }
}
