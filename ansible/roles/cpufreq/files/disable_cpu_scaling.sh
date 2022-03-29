#!/usr/bin/env bash

if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
  for i in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo "performance" > $i; done
fi

if [[ -f /sys/devices/system/cpu/cpu0/cpuidle/state0/disable ]]; then
  for i in /sys/devices/system/cpu/cpu*/cpuidle/state*/disable; do echo 1 > $i; done
fi

if [[ -f /sys/devices/system/cpu/intel_pstate/no_turbo ]]; then 
  echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo
fi
