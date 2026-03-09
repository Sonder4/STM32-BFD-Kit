# STM32CubeMX IOC文件格式参考

## 文件概述

.ioc文件是STM32CubeMX项目的配置文件，采用键值对格式存储硬件配置信息。

## 基本格式

```
#MicroXplorer Configuration settings - do not modify
KEY1=VALUE1
KEY2=VALUE2
...
```

## 主要配置类别

### 1. MCU信息

| 键前缀 | 说明 |
|--------|------|
| `Mcu.Name` | MCU型号名称 |
| `Mcu.UserName` | 用户选择的MCU型号 |
| `Mcu.Family` | MCU系列 (STM32F4等) |
| `Mcu.Package` | 封装类型 |
| `Mcu.CPN` | 完整零件编号 |
| `Mcu.IP{n}` | 第n个IP外设 |
| `Mcu.IPNb` | IP外设总数 |
| `Mcu.Pin{n}` | 第n个引脚配置 |
| `Mcu.PinsNb` | 引脚总数 |

### 2. 项目管理

| 键前缀 | 说明 |
|--------|------|
| `ProjectManager.ProjectName` | 项目名称 |
| `ProjectManager.TargetToolchain` | 目标工具链 |
| `ProjectManager.FirmwarePackage` | 固件包版本 |
| `ProjectManager.HeapSize` | 堆大小 |
| `ProjectManager.StackSize` | 栈大小 |

### 3. RCC时钟配置

| 键前缀 | 说明 |
|--------|------|
| `RCC.SYSCLKFreq_VALUE` | 系统时钟频率 |
| `RCC.HCLKFreq_Value` | AHB总线频率 |
| `RCC.APB1Freq_Value` | APB1总线频率 |
| `RCC.APB2Freq_Value` | APB2总线频率 |
| `RCC.PLLM/N/Q` | PLL参数 |
| `RCC.HSE_VALUE` | 外部晶振频率 |

### 4. 外设配置格式

```
<外设名>.<参数名>=<值>
```

示例:
```
CAN1.BS1=CAN_BS1_10TQ
CAN1.Prescaler=3
CAN1.CalculateBaudRate=1000000
USART1.VirtualMode=VM_ASYNC
SPI4.Mode=SPI_MODE_MASTER
```

### 5. GPIO引脚配置

| 键模式 | 说明 |
|--------|------|
| `<PIN>.Signal` | 引脚信号功能 |
| `<PIN>.GPIO_Label` | 用户定义标签 |
| `<PIN>.Locked` | 是否锁定配置 |
| `<PIN>.GPIOParameters` | GPIO参数列表 |
| `<PIN>.PinState` | 初始状态 |

### 6. DMA配置

| 键模式 | 说明 |
|--------|------|
| `Dma.RequestsNb` | DMA请求数量 |
| `Dma.Request{n}` | 第n个DMA请求 |
| `Dma.<请求名>.<n>.Instance` | DMA实例 |
| `Dma.<请求名>.<n>.Direction` | 传输方向 |
| `Dma.<请求名>.<n>.Mode` | DMA模式 |

### 7. NVIC中断配置

格式:
```
NVIC.<IRQ名称>=<enabled>:<抢占优先级>:<子优先级>:...
```

示例:
```
NVIC.CAN1_RX0_IRQn=true:5:0:false:false:true:true:true:true
NVIC.USART1_IRQn=true:5:0:false:false:true:true:true:true
```

### 8. 定时器配置

| 键模式 | 说明 |
|--------|------|
| `TIMn.Prescaler` | 预分频值 |
| `TIMn.Period` | 周期值 |
| `TIMn.Channel-PWM Generation...` | PWM通道配置 |
| `SH.S_TIMn_CHx.0` | 定时器通道信号 |

### 9. FreeRTOS配置

| 键前缀 | 说明 |
|--------|------|
| `FREERTOS.configTOTAL_HEAP_SIZE` | 总堆大小 |
| `FREERTOS.Tasks01` | 任务定义 |
| `FREERTOS.configENABLE_FPU` | FPU使能 |

## 常用值解析

### CAN时序参数

- `CAN_BS1_10TQ`: 位段1为10个时间量子
- `CAN_BS2_3TQ`: 位段2为3个时间量子
- 波特率计算: BaudRate = PCLK / (Prescaler × (1 + BS1 + BS2))

### SPI模式

- `SPI_MODE_MASTER`: 主机模式
- `SPI_MODE_SLAVE`: 从机模式
- `SPI_DIRECTION_2LINES`: 全双工

### GPIO模式

- `GPIO_Output`: 推挽输出
- `GPIO_Input`: 浮空输入
- `GPXTI`: 外部中断

## 注意事项

1. 文件首行 `#MicroXplorer Configuration settings - do not modify` 不要修改
2. 键值对区分大小写
3. 部分值包含特殊字符(如`\:`)需要转义处理
4. 配置顺序不影响功能，但建议保持原有顺序
