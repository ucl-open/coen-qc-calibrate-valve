using Bonsai;
using OpenRigs.Devices;
using System;
using System.ComponentModel;
using System.Reactive.Linq;

// Water delivered at a reward's pulse width (Pip, 11 Nov 2026: "select a reward size ... and also offer
// to deliver 1 ml of water with clicks of that length"): app-rig-control's Calibrations page works out
// the width and the pulses from the valve's curve and launches deliver.bonsai with them and the
// curve's pulseGapMs, so the water is fired as the calibration fired it (OpenRigs.Core FirePulses).
// Compiled by Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    [Combinator]
    [Description("At each input, one burst for FirePulses: Pulses pulses of PulseWidthMs on the valve's line at PulseGapMs. Input: (anything, the valve's wiring, OpenRigs.Devices WiredRewardValve); stops the workflow if a setting is out of range.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class DeliverTrain
    {
        int pulseWidthMs = 1;
        int pulses;
        int pulseGapMs;

        [Description("Each pulse's width in ms: the reward's, read off the valve's curve.")]
        public int PulseWidthMs
        {
            get { return pulseWidthMs; }
            set { pulseWidthMs = value; }
        }

        [Description("How many pulses to fire.")]
        public int Pulses
        {
            get { return pulses; }
            set { pulses = value; }
        }

        [Description("The off-to-on time between pulses, in ms: the valve's calibration file's pulseGapMs.")]
        public int PulseGapMs
        {
            get { return pulseGapMs; }
            set { pulseGapMs = value; }
        }

        public IObservable<PulseTrain> Process<TSource>(IObservable<Tuple<TSource, RewardValveWiring>> source)
        {
            return source.Select(input =>
            {
                if (Pulses < 1 || Pulses > 5000)
                {
                    throw new InvalidOperationException(string.Format("Pulses {0} is not a delivery: give 1 to 5000.", Pulses));
                }
                if (PulseWidthMs < 1 || PulseWidthMs > 1000)
                {
                    throw new InvalidOperationException(string.Format("PulseWidthMs {0} is not a pulse width: give 1 to 1000 ms.", PulseWidthMs));
                }
                if (PulseGapMs < 1 || PulseGapMs > 10000)
                {
                    throw new InvalidOperationException(string.Format("PulseGapMs {0} is not a gap: give the valve calibration file's pulseGapMs, 1 to 10000 ms.", PulseGapMs));
                }
                return new PulseTrain { Line = input.Item2.Line.ToString(), PulseWidthMs = PulseWidthMs, Pulses = Pulses, PulseGapMs = PulseGapMs };
            });
        }
    }
}
