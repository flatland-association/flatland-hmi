import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { MapCell } from '../renderer.service';
import { Agent } from '../data.service';

type MapRow = MapCell[]
type Map = MapRow[]

interface FlatlandEnvCell {
  href: string
  target: boolean
  cls?: string
}

interface FlatlandAgent {
  position: [number, number]
  cssClass: string
  cssStyle: string
}

@Component({
  selector: 'app-flatland-gridworld',
  imports: [],
  templateUrl: './flatland-gridworld.component.html',
  styleUrl: './flatland-gridworld.component.scss'
})
export class FlatlandGridworldComponent implements OnChanges {
  @Input() map: Map = []
  @Input() agents: Agent[] = []

  public width = 1 // in cells
  public height = 1 // in cells

  public flatlandMap: FlatlandEnvCell[][] = []
  public flatlandAgents: FlatlandAgent[] = []

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['map']) {
      this.height = this.map.length
      this.width = this.map.reduce((max, row) => Math.max(max, row.length), 0)
      this.flatlandMap = this.map.map((row) => {
        return row.map((cell) => {
          const groundClass = cell.ground.split(' ').find((cls) => cls.startsWith('bkgnd_') || cls.startsWith('transition_')) ?? 'none'
          const rotation = cell.ground.split(' ').find((cls) => cls.startsWith('rotation_'))
          return {
            href: `#${groundClass}`,
            target: !!cell.objects,
            cls: rotation,
          }
        })
      })
    }
    if (changes['agents']) {
      this.flatlandAgents = this.agents.map((a, i) => {
        return {
          position: [a.position?.[1] ?? -1, a.position?.[0] ?? -1],
          cssClass: `rotation_${a.direction * 90} ${a.malfunction > 0 ? 'malfunction' : ''}`,
          cssStyle: `--train-hue: ${25 + 360 / this.agents.length * i}`
        } satisfies FlatlandAgent
      }).filter((a) => a.position[0] >= 0)
    }
  }
}
