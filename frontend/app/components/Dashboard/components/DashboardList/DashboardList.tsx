import { observer } from 'mobx-react-lite';
import React from 'react';
import { NoContent, Pagination } from 'UI';
import { useStore } from 'App/mstore';
import { sliceListPerPage } from 'App/utils';
import DashboardListItem from './DashboardListItem';
import AnimatedSVG, { ICONS } from 'Shared/AnimatedSVG/AnimatedSVG';

function DashboardList() {
  const { dashboardStore } = useStore();
  const list = dashboardStore.filteredList;
  const dashboardsSearch = dashboardStore.dashboardsSearch;
  const lenth = list.length;

  return (
    <NoContent
      show={lenth === 0}
      title={
        <div className="flex flex-col items-center justify-center">
          <div className="text-center my-4">
            {dashboardsSearch !== '' ? (
              'No matching results'
            ) : (
              <div>
                <div>Create your first Dashboard</div>
                <div className="text-sm color-gray-medium font-normal">
                  A dashboard lets you visualize trends and insights of data captured by OpenReplay.
                </div>
              </div>
            )}
          </div>
          <AnimatedSVG name={ICONS.NO_DASHBOARDS} size={180} />
        </div>
      }
    >
      <div className="mt-3 border-b">
        <div className="grid grid-cols-12 py-2 font-medium px-6">
          <div className="col-span-8">Title</div>
          <div className="col-span-2">Visibility</div>
          <div className="col-span-2 text-right">Creation Date</div>
        </div>

        {sliceListPerPage(list, dashboardStore.page - 1, dashboardStore.pageSize).map(
          (dashboard: any) => (
            <React.Fragment key={dashboard.dashboardId}>
              <DashboardListItem dashboard={dashboard} />
            </React.Fragment>
          )
        )}
      </div>

      <div className="w-full flex items-center justify-between pt-4 px-6">
        <div className="text-disabled-text">
          Showing{' '}
          <span className="font-semibold">{Math.min(list.length, dashboardStore.pageSize)}</span>{' '}
          out of <span className="font-semibold">{list.length}</span> Dashboards
        </div>
        <Pagination
          page={dashboardStore.page}
          totalPages={Math.ceil(lenth / dashboardStore.pageSize)}
          onPageChange={(page) => dashboardStore.updateKey('page', page)}
          limit={dashboardStore.pageSize}
          debounceRequest={100}
        />
      </div>
    </NoContent>
  );
}

export default observer(DashboardList);
