import time


class PIDController:
    proportionalGain: float
    integralGain: float
    derivativeGain: float

    minValue: float
    maxValue: float
    thresholdValue: float

    minOutput: float
    maxOutput: float

    __derInited: bool = False

    lastError: float = 0
    lastD: float = 0
    lastTime: float = 0

    integrationStored: float = 0
    integralSaturation: float

    def __init__(self,
                 P: float = 1,
                 I: float = .5,
                 D: float = 2,
                 integralSaturation: float = 100,

                 minVal=-100,
                 maxVal=100,
                 thresholdVal=100.0,

                 minOut=-500,
                 maxOut=500
                 ) -> None:
        self.proportionalGain = P
        self.integralGain = I
        self.derivativeGain = D
        self.integralSaturation = integralSaturation

        self.minValue = minVal
        self.maxValue = maxVal
        self.thresholdValue = thresholdVal

        self.minOutput = minOut
        self.maxOutput = maxOut

    @staticmethod
    def clamp(val: float, minVal: float, maxVal: float) -> float:
        return max(minVal, min(val, maxVal))

    @staticmethod
    def lerp(a: float, b: float, t: float):
        return a + (b - a) * t

    def reset(self):
        self.lastError = 0
        self.lastTime = 0
        self.integrationStored = 0
        self.lastD = 0
        self.__derInited = False

    def update(self, error: float) -> float:
        updateTime = time.time()
        dt = updateTime - self.lastTime
        if dt < 1e-6:
            dt = 1e-6
        self.lastTime = updateTime

        P = self.proportionalGain * error

        self.integrationStored = self.clamp(
            self.integrationStored + (error * dt),
            -self.integralSaturation, self.integralSaturation
        )
        I = self.integralGain * self.integrationStored

        deriveMeasure = 0

        if self.__derInited:
            deriveMeasure = (error - self.lastError) / dt
        else:
            self.__derInited = True

        self.lastError = error

        D = self.derivativeGain * deriveMeasure
        D = self.lerp(self.lastD, D, 0.25)

        self.lastD = D

        result = P + I + D
        result = self.clamp(result, self.minValue, self.maxValue)

        k = abs(error) / self.thresholdValue

        return self.clamp(result * (k if k > 1 else 1), self.minOutput, self.maxOutput)
