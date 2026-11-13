using Bonsai;
using OpenRigs.Devices;
using System;
using System.ComponentModel;
using System.Linq;
using System.Reactive.Linq;

// The spouts during a calibration (Pip, 10 Nov 2026: the drops land as in a session), on
// OpenRigs.Devices HarpLickSpoutStage, which homes the stage and moves the spouts in. Compiled by
// Bonsai under C# 5.
namespace CoenQcCalibrateValve
{
    [Combinator]
    [Description("Each stage target with both radial (in/out) axes at RadialSteps from home, the rest kept; 0 keeps the target as it is.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class SpoutsForward
    {
        [Description("Steps from home for both radial axes; 0 leaves the target unchanged.")]
        public int RadialSteps { get; set; }

        public IObservable<SpoutPositions> Process(IObservable<SpoutPositions> source)
        {
            return source.Select(target => Forward(target, RadialSteps));
        }

        public static SpoutPositions Forward(SpoutPositions target, int steps)
        {
            if (steps == 0) return target;
            var values = target.ToArray();
            values[1] = values[2] = steps;
            return SpoutPositions.FromArray(values);
        }
    }

    [Combinator]
    [Description("Each stage target, passed on once the stage has had time to reach it from home: 0.5 s plus 280 us a step on its farthest axis (the drivers' step interval).")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class WaitForMove
    {
        public IObservable<SpoutPositions> Process(IObservable<SpoutPositions> source)
        {
            return source.SelectMany(target => Observable.Timer(MoveTime(target)).Select(_ => target));
        }

        public static TimeSpan MoveTime(SpoutPositions target)
        {
            return TimeSpan.FromSeconds(0.5 + 0.00028 * target.ToArray().Max(steps => Math.Abs(steps)));
        }
    }
}
