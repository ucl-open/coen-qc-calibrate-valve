using Bonsai;
using System;
using System.ComponentModel;
using System.Reactive.Linq;

// Water delivered at a reward's pulse width (Pip, 11 Nov 2026: "select a reward size ... and also offer
// to deliver 1 ml of water with clicks of that length"): rig-control's Calibrations page works out
// the width and the pulses from the valve's curve and launches deliver.bonsai with them and the
// curve's pulseGapMs, so the water is fired as the calibration fired it (OpenRigs.Core FirePulses).
// Compiled by Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    [Combinator]
    [Description("At each input, one burst for FirePulses: Pulses pulses of SizeMs on Channel at PulseGapMs. Input: (anything, rig.yml's valves); stops the workflow if Channel is not a RewardValve in rig.yml's wiring or a setting is out of range.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class DeliverTrain
    {
        int channel = 1;
        int sizeMs = 1;
        int pulses;
        int pulseGapMs;

        [Description("The valve's behavior board line, 1 to 3 (DO1 to DO3).")]
        public int Channel
        {
            get { return channel; }
            set { channel = value; }
        }

        [Description("Each pulse's width in ms: the reward's, read off the valve's curve.")]
        public int SizeMs
        {
            get { return sizeMs; }
            set { sizeMs = value; }
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

        public IObservable<PulseTrain> Process<TSource>(IObservable<Tuple<TSource, ValveRig>> source)
        {
            return source.Select(input =>
            {
                if (Pulses < 1 || Pulses > 5000)
                {
                    throw new InvalidOperationException(string.Format("Pulses {0} is not a delivery: give 1 to 5000.", Pulses));
                }
                if (SizeMs < 1 || SizeMs > 1000)
                {
                    throw new InvalidOperationException(string.Format("SizeMs {0} is not a pulse width: give 1 to 1000 ms.", SizeMs));
                }
                if (PulseGapMs < 1 || PulseGapMs > 10000)
                {
                    throw new InvalidOperationException(string.Format("PulseGapMs {0} is not a gap: give the valve calibration file's pulseGapMs, 1 to 10000 ms.", PulseGapMs));
                }
                input.Item2.Check(new[] { Channel });
                return new PulseTrain { Line = Channel, WidthMs = SizeMs, Count = Pulses, PulseGapMs = PulseGapMs };
            });
        }
    }
}
