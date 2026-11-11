using Bonsai;
using OpenRigs.Core;
using System;
using System.ComponentModel;
using System.Reactive.Linq;

// Water delivered at a reward's pulse width (Pip, 11 Nov 2026: "select a reward size ... and also offer
// to deliver 1 ml of water with clicks of that length"): rig-control's Calibrations page works out
// the width and the pulses from the valve's curve and launches deliver.bonsai with them. Compiled by
// Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    [Combinator]
    [Description("At each input, fires Pulses pulse requests of SizeMs on Channel, one every SizeMs plus InterPulseIntervalMs (OpenRigs.Core PulseBurst), completing one period after the last so its drop can land.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class DeliverBurst
    {
        int channel = 1;
        int sizeMs = 1;
        int pulses;
        int interPulseIntervalMs = 80;

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

        [Description("The gap after each pulse, in ms.")]
        public int InterPulseIntervalMs
        {
            get { return interPulseIntervalMs; }
            set { interPulseIntervalMs = value; }
        }

        public IObservable<Tuple<int, int>> Process<TSource>(IObservable<TSource> source)
        {
            return source.SelectMany(_ =>
            {
                if (Channel < 1 || Channel > 3)
                {
                    throw new InvalidOperationException(string.Format("Channel {0} is not a behavior board line (1 to 3).", Channel));
                }
                if (Pulses < 1 || Pulses > 5000)
                {
                    throw new InvalidOperationException(string.Format("Pulses {0} is not a delivery: give 1 to 5000.", Pulses));
                }
                if (SizeMs < 1 || SizeMs > 1000)
                {
                    throw new InvalidOperationException(string.Format("SizeMs {0} is not a pulse width: give 1 to 1000 ms.", SizeMs));
                }
                return PulseBurst.Burst(Channel, SizeMs, Pulses, InterPulseIntervalMs);
            });
        }
    }
}
